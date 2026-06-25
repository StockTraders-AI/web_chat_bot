import json
import httpx

from services.ticker_policy import sanitize_api_result
from datetime import datetime
import re
import unicodedata

API_BASE = "https://stocktradersai.vn"

SUPPORTED_CONDITION_KEYS = {
    "waitbuy_over_200",
    "vnindex_down_10_waitbuy_reversal",
    "core_branch_smdt_cross_70",
    "core_branch_smdt_cross_70_cashflow_in",
    "smdt_ticker_cross_70_prev_up",
    "smdt_up_3_sessions",
    "smdt_branch_up_3_sessions",
}


async def post_data_api(endpoint: str, params: dict | None = None):
    url = f"{API_BASE}/service/data/{endpoint}"

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(40.0, connect=10.0)
        ) as client:
            res = await client.post(url, params=params or {})
            res.raise_for_status()
            return sanitize_api_result(endpoint, res.json())

    except httpx.ReadTimeout:
        return {
            "_error": True,
            "type": "timeout",
            "message": f"API {endpoint} timeout",
            "endpoint": endpoint,
            "params": params or {},
        }

    except Exception as e:
        return {
            "_error": True,
            "type": "api_error",
            "message": str(e),
            "endpoint": endpoint,
            "params": params or {},
        }


def is_api_error(data):
    return isinstance(data, dict) and data.get("_error")


def to_float(value, default=0):
    try:
        return float(value or default)
    except Exception:
        return default


def parse_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def extract_flow_condition_ids(expression: str) -> list[int]:
    ids = []

    for part in str(expression or "").split():
        if part.isdigit():
            ids.append(int(part))

    return ids


def resolve_flow_condition_refs(
    expression: str,
    templates: list[dict],
) -> list[dict]:
    parts = str(expression or "").strip().split()
    refs = []
    pending_operator = ""
    confirmed_templates = [
        template for template in templates
        if template.get("status") == "confirmed"
    ]
    by_id = {
        int(template["id"]): template
        for template in confirmed_templates
        if str(template.get("id", "")).isdigit()
    }

    for part in parts:
        upper = part.upper()

        if upper in {"AND", "OR"}:
            pending_operator = upper
            continue

        if part.isdigit() and int(part) in by_id:
            refs.append({
                "id": int(part),
                "operator": pending_operator if refs else "",
            })
            pending_operator = ""

    if refs:
        return refs

    normalized_expression = normalize_condition_text(expression)

    for template in confirmed_templates:
        candidates = [
            template.get("name") or "",
            template.get("condition_logic") or "",
        ]

        if any(
            normalize_condition_text(candidate) == normalized_expression
            for candidate in candidates
        ):
            return [{
                "id": int(template["id"]),
                "operator": "",
            }]

    return []


def evaluate_flow_expression(expression: str, matches: dict[int, bool]) -> bool:
    parts = str(expression or "").strip().split()
    result = None
    pending_operator = "AND"

    for part in parts:
        upper = part.upper()

        if upper in {"AND", "OR"}:
            pending_operator = upper
            continue

        if not part.isdigit():
            continue

        current = bool(matches.get(int(part)))

        if result is None:
            result = current
        elif pending_operator == "OR":
            result = result or current
        else:
            result = result and current

        pending_operator = "AND"

    return bool(result)


def normalize_condition_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    normalized = "".join(
        char for char in normalized
        if unicodedata.category(char) != "Mn"
    )
    normalized = normalized.lower()
    normalized = normalized.replace("and", " ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def resolve_condition_key(condition_logic: str) -> str:
    raw = (condition_logic or "").strip()

    if raw in {
        "waitbuy_over_200",
        "vnindex_down_10_waitbuy_reversal",
        "core_branch_smdt_cross_70",
        "core_branch_smdt_cross_70_cashflow_in",
        "smdt_ticker_cross_70_prev_up",
        "smdt_up_3_sessions",
        "smdt_branch_up_3_sessions",
    }:
        return raw

    normalized = normalize_condition_text(raw)

    if (
        "nganh" in normalized
        and "smdt" in normalized
        and "70" in normalized
        and "cashflow" in normalized
        and "2" in normalized
    ):
        return "core_branch_smdt_cross_70_cashflow_in"

    if (
        "smdt" in normalized
        and "70" in normalized
        and "cross" in normalized
        and "1" in normalized
        and "2" in normalized
        and "nganh" not in normalized
    ):
        return "smdt_ticker_cross_70_prev_up"

    if (
        "nganh" in normalized
        and "smdt" in normalized
        and "70" in normalized
        and (
            "cross" in normalized
            or "chu luc" in normalized
            or "vuot" in normalized
        )
    ):
        return "core_branch_smdt_cross_70"

    if (
        "nganh" in normalized
        and "smdt" in normalized
        and "1" in normalized
        and "2" in normalized
        and normalized.count("smdt") >= 3
    ):
        return "smdt_branch_up_3_sessions"

    if (
        "smdt" in normalized
        and "1" in normalized
        and "2" in normalized
        and normalized.count("smdt") >= 3
    ):
        return "smdt_up_3_sessions"

    if (
        "vnindex" in normalized
        and "close" in normalized
        and "10" in normalized
        and ("waitbuy" in normalized or "cho mua" in normalized)
        and "60" in normalized
        and "20" in normalized
    ):
        return "vnindex_down_10_waitbuy_reversal"

    if (
        ("waitbuy" in normalized or "cho mua" in normalized)
        and "200" in normalized
    ):
        return "waitbuy_over_200"

    return raw


def resolve_template_support(template: dict) -> dict:
    name = str(template.get("name") or "").strip()
    logic = str(template.get("condition_logic") or "").strip()
    resolved_key = resolve_condition_key(f"{name} {logic}".strip())

    return {
        **template,
        "resolved_condition_key": resolved_key,
        "support_status": (
            "supported"
            if resolved_key in SUPPORTED_CONDITION_KEYS
            else "unsupported"
        ),
    }


async def condition_waitbuy_over_200(context: dict):
    date = context.get("date")

    if not date:
        return {
            "ok": False,
            "matched": False,
            "message": "Thiếu date để kiểm tra waitbuy > 200",
        }

    raw = await post_data_api(
        "getStockWave",
        {"date": date},
    )

    if is_api_error(raw):
        return {
            "ok": False,
            "matched": False,
            "message": raw["message"],
            "error": raw,
        }

    rows = []

    if isinstance(raw, dict):
        rows = raw.get("waveDatas") or raw.get("data") or []

    if not rows:
        return {
            "ok": False,
            "matched": False,
            "message": "Không có dữ liệu getStockWave",
            "raw": raw,
        }

    latest = rows[-1]

    waitbuy = to_float(
        latest.get("waitbuy")
        or latest.get("waitBuy")
        or latest.get("cho_mua")
    )

    matched = waitbuy > 200

    return {
        "ok": True,
        "matched": matched,
        "condition_key": "waitbuy_over_200",
        "condition": "waitbuy > 200",
        "data": {
            "date": latest.get("date") or date,
            "waitbuy": waitbuy,
        },
        "message": (
            "Chờ mua tăng trên 200 cổ phiếu"
            if matched
            else "Không đạt điều kiện"
        ),
    }


def extract_rows(raw, list_keys: tuple[str, ...]) -> list[dict]:
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]

    if not isinstance(raw, dict):
        return []

    for key in list_keys:
        value = raw.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]

    data = raw.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]

    if isinstance(data, dict):
        for key in list_keys:
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]

    return []


def row_date(row: dict):
    return row.get("date") or row.get("tradingDate") or row.get("time")


def scan_vnindex_waitbuy_reversal(
    total_trade_rows: list[dict],
    wave_rows: list[dict],
) -> dict:
    trade_by_date = {}
    for row in total_trade_rows:
        date = row_date(row)
        close = to_float(row.get("close"), default=None)
        if date and close is not None:
            trade_by_date[date] = {
                "date": date,
                "close": close,
            }

    wave_by_date = {}
    for row in wave_rows:
        date = row_date(row)
        waitbuy = to_float(
            row.get("waitbuy")
            or row.get("waitBuy")
            or row.get("wait_buy")
            or row.get("cho_mua"),
            default=None,
        )
        if date and waitbuy is not None:
            wave_by_date[date] = {
                "date": date,
                "waitbuy": waitbuy,
                "buy": row.get("buy"),
                "sell": row.get("sell"),
                "total": row.get("total"),
                "waitsell": row.get("waitsell") or row.get("waitSell") or row.get("wait_sell"),
                "reliability": row.get("reliability"),
            }

    common_dates = sorted(set(trade_by_date) & set(wave_by_date))
    matches = []

    for index in range(1, len(common_dates)):
        prev_date = common_dates[index - 1]
        date = common_dates[index]
        prev_trade = trade_by_date[prev_date]
        trade = trade_by_date[date]
        prev_wave = wave_by_date[prev_date]
        wave = wave_by_date[date]
        close_change = trade["close"] - prev_trade["close"]
        waitbuy_change = wave["waitbuy"] - prev_wave["waitbuy"]

        if (
            close_change <= -10
            and prev_wave["waitbuy"] < 60
            and wave["waitbuy"] > 60
            and waitbuy_change >= 20
        ):
            matches.append({
                "date": date,
                "prev_date": prev_date,
                "close": trade["close"],
                "prev_close": prev_trade["close"],
                "close_change": close_change,
                "waitbuy": wave["waitbuy"],
                "prev_waitbuy": prev_wave["waitbuy"],
                "waitbuy_change": waitbuy_change,
                "buy": wave.get("buy"),
                "sell": wave.get("sell"),
                "total": wave.get("total"),
                "waitsell": wave.get("waitsell"),
                "reliability": wave.get("reliability"),
            })

    return {
        "matched": bool(matches),
        "count": len(matches),
        "latest": matches[-1] if matches else None,
        "matches": matches,
    }


async def condition_vnindex_down_10_waitbuy_reversal(context: dict):
    raw_date = str(context.get("date") or datetime.now().year)
    year = raw_date[:4] if raw_date[:4].isdigit() else str(datetime.now().year)

    total_raw = await post_data_api(
        "getTotalTrade",
        {
            "ticker": "VNINDEX",
            "date": year,
        },
    )
    wave_raw = await post_data_api(
        "getStockWave",
        {
            "date": year,
        },
    )

    for raw in [total_raw, wave_raw]:
        if is_api_error(raw):
            return {
                "ok": False,
                "matched": False,
                "condition_key": "vnindex_down_10_waitbuy_reversal",
                "message": raw["message"],
                "error": raw,
            }

    total_trade_rows = extract_rows(
        total_raw,
        ("totalTradeDatas", "tradeDatas", "records", "items"),
    )
    wave_rows = extract_rows(
        wave_raw,
        ("waveDatas", "stockWaveDatas", "items"),
    )
    scan = scan_vnindex_waitbuy_reversal(total_trade_rows, wave_rows)
    latest = scan["latest"]

    return {
        "ok": True,
        "matched": scan["matched"],
        "condition_key": "vnindex_down_10_waitbuy_reversal",
        "condition": "VNINDEX close giam >= 10, waitbuy tu <60 len >60 va tang >=20",
        "count": scan["count"],
        "data": {
            "year": year,
            "latest": latest,
            "matches": scan["matches"],
        },
        "message": (
            f"Gan nhat la {latest['date']}: VNINDEX giam {abs(latest['close_change']):g} diem, "
            f"cho mua tang tu {latest['prev_waitbuy']:g} len {latest['waitbuy']:g}"
            if latest
            else "Khong co phien nao thoa dieu kien VNINDEX giam va cho mua tang manh"
        ),
    }


async def condition_core_branch_smdt_cross_70(context: dict):
    date = context.get("date")

    if not date:
        return {
            "ok": False,
            "matched": False,
            "message": "Thiếu date để kiểm tra ngành chủ lực dẫn sóng",
        }

    raw = await post_data_api(
        "getCoreBranchLeader",
        {"date": date},
    )

    if is_api_error(raw):
        return {
            "ok": False,
            "matched": False,
            "message": raw["message"],
            "error": raw,
        }

    branches = []

    if isinstance(raw, dict):
        branches = raw.get("branches") or []

    matched = len(branches) > 0

    return {
        "ok": True,
        "matched": matched,
        "condition_key": "core_branch_smdt_cross_70",
        "condition": "CoreBranchLeader SMDT >= 70",
        "data": {
            "date": raw.get("date") if isinstance(raw, dict) else date,
            "branches": branches,
        },
        "message": (
            "Có ngành chủ lực dẫn sóng"
            if matched
            else "Không có ngành chủ lực dẫn sóng"
        ),
    }

async def condition_smdt_up_3_sessions(context: dict):
    params = {}

    if context.get("ticker"):
        params["ticker"] = context.get("ticker")

    raw = await post_data_api(
        "getSMDTIncreasing3",
        params,
    )

    if is_api_error(raw):
        return {
            "ok": False,
            "matched": False,
            "condition_key": "smdt_up_3_sessions",
            "message": raw["message"],
            "error": raw,
        }

    result = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
    result = [
        item for item in result
        if isinstance(item, dict)
    ]

    return {
        "ok": True,
        "matched": len(result) > 0,
        "condition_key": "smdt_up_3_sessions",
        "condition": "SMDT tăng 3 phiên liên tiếp",
        "count": len(result),
        "data": result,
        "message": (
            "Có mã SMDT tăng 3 phiên liên tiếp"
            if result
            else "Không có mã SMDT tăng 3 phiên liên tiếp"
        ),
    }


def get_smdt_rows(raw):
    if isinstance(raw, dict):
        rows = raw.get("SMDTDatas") or raw.get("data") or []
        return rows if isinstance(rows, list) else []

    return raw if isinstance(raw, list) else []


def get_recent_smdt_points(item: dict, max_date: str | None = None):
    points = []

    for point in item.get("smdts") or item.get("points") or item.get("data") or []:
        if not isinstance(point, dict):
            continue

        point_date = point.get("date")

        if max_date and point_date and point_date > max_date:
            continue

        points.append({
            "date": point_date or "",
            "smdt": to_float(point.get("smdt")),
        })

    points = sorted(points, key=lambda value: value["date"])
    return points[-3:]


async def condition_smdt_ticker_cross_70_prev_up(context: dict):
    date = context.get("date")
    params = {}

    if date:
        params["date"] = date

    if context.get("ticker"):
        params["keyValue"] = context.get("ticker")

    raw = await post_data_api(
        "getSMDTTickerCross",
        params,
    )

    if is_api_error(raw):
        return {
            "ok": False,
            "matched": False,
            "condition_key": "smdt_ticker_cross_70_prev_up",
            "message": raw["message"],
            "error": raw,
        }

    matches = []

    for item in get_smdt_rows(raw):
        if not isinstance(item, dict):
            continue

        recent = get_recent_smdt_points(item, date)

        if len(recent) < 3:
            continue

        before_previous, previous, current = recent

        if current["smdt"] >= 70 and previous["smdt"] > before_previous["smdt"]:
            matches.append({
                "ticker": item.get("keyValue") or item.get("ticker") or "",
                "name": item.get("keyName") or item.get("name") or "",
                "dates": [point["date"] for point in recent],
                "smdt_last3": [point["smdt"] for point in recent],
            })

    return {
        "ok": True,
        "matched": len(matches) > 0,
        "condition_key": "smdt_ticker_cross_70_prev_up",
        "condition": "SMDT co phieu vuot 70 va SMDT hom qua tang",
        "count": len(matches),
        "data": matches,
        "message": (
            "Co ma SMDT vuot 70 va SMDT hom qua tang"
            if matches
            else "Khong co ma SMDT vuot 70 va SMDT hom qua tang"
        ),
    }


def get_smdt_branch_rows(raw):
    rows = get_smdt_rows(raw)

    if rows:
        return rows

    if isinstance(raw, dict):
        rows = raw.get("branches") or []
        return rows if isinstance(rows, list) else []

    return []


def get_recent_branch_smdt_points(branch: dict, max_date: str | None = None):
    return get_recent_smdt_points(branch, max_date)


def first_text_value(item: dict, keys: list[str]) -> str:
    for key in keys:
        value = item.get(key)

        if value:
            return str(value)

    return ""


def extract_demo_items(result: dict) -> list[str]:
    condition_key = result.get("condition_key")
    data = result.get("data")

    if condition_key == "core_branch_smdt_cross_70" and isinstance(data, dict):
        data = data.get("branches") or []

    if not isinstance(data, list):
        return []

    items = []

    for item in data:
        if not isinstance(item, dict):
            continue

        if condition_key == "smdt_up_3_sessions":
            value = first_text_value(item, ["ticker", "symbol", "code"])
        elif condition_key in {
            "smdt_branch_up_3_sessions",
            "core_branch_smdt_cross_70",
            "core_branch_smdt_cross_70_cashflow_in",
        }:
            value = first_text_value(
                item,
                ["branch", "keyName", "name", "keyValue", "path"],
            )
        else:
            value = first_text_value(
                item,
                ["ticker", "branch", "keyName", "name", "keyValue"],
            )

        if value and value not in items:
            items.append(value)

    return items


def format_demo_number(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    return f"{number:.2f}".rstrip("0").rstrip(".")


def format_smdt_percent(value) -> str:
    return f"{format_demo_number(value)}%"


def extract_demo_item_details(result: dict, limit: int = 5) -> list[str]:
    condition_key = result.get("condition_key")
    data = result.get("data")

    if condition_key == "vnindex_down_10_waitbuy_reversal" and isinstance(data, dict):
        latest = data.get("latest")

        if isinstance(latest, dict):
            return [
                (
                    f"{latest.get('date')}: VNINDEX giam "
                    f"{format_demo_number(abs(to_float(latest.get('close_change'))))} diem; "
                    f"cho mua {format_demo_number(latest.get('prev_waitbuy'))} -> "
                    f"{format_demo_number(latest.get('waitbuy'))}"
                )
            ]

        return []

    if condition_key == "core_branch_smdt_cross_70" and isinstance(data, dict):
        data = data.get("branches") or []

    if not isinstance(data, list):
        return []

    details = []

    for item in data:
        if not isinstance(item, dict):
            continue

        label = first_text_value(
            item,
            ["ticker", "branch", "keyName", "name", "keyValue", "path"],
        )

        if not label:
            continue

        parts = [label]
        smdt_last3 = item.get("smdt_last3")

        if isinstance(smdt_last3, list) and smdt_last3:
            smdt_text = " > ".join(format_smdt_percent(value) for value in smdt_last3)
            parts.append(f"SMDT {smdt_text}")

        dates = item.get("dates")

        if isinstance(dates, list) and dates:
            parts.append(f"ngay {', '.join(str(value) for value in dates)}")

        cashflow = item.get("cashflow") or item.get("cashFlow") or item.get("content")

        if cashflow:
            parts.append(str(cashflow))

        details.append(": ".join([parts[0], "; ".join(parts[1:])]) if len(parts) > 1 else parts[0])

        if len(details) >= limit:
            break

    return details


def extract_demo_raw_items(result: dict) -> list[dict]:
    data = result.get("data")

    if result.get("condition_key") == "vnindex_down_10_waitbuy_reversal" and isinstance(data, dict):
        latest = data.get("latest")
        return [latest] if isinstance(latest, dict) else []

    if result.get("condition_key") == "core_branch_smdt_cross_70" and isinstance(data, dict):
        data = data.get("branches") or []

    if isinstance(data, dict):
        return [data]

    if not isinstance(data, list):
        return []

    return [item for item in data if isinstance(item, dict)]


def get_nested_demo_value(item: dict, path: str):
    current = item

    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return ""

        if current is None:
            return ""

    if isinstance(current, float):
        return format_demo_number(current)

    if isinstance(current, int):
        return str(current)

    if isinstance(current, list):
        return ", ".join(format_demo_number(value) for value in current)

    return str(current)


def render_demo_item_blocks(prompt: str, items: list[dict], limit: int = 5) -> str:
    pattern = re.compile(r"\{\{#items\}\}([\s\S]*?)\{\{/items\}\}")

    def replace_block(match):
        template = match.group(1)
        rows = []

        for item in items[:limit]:
            row = template

            for token in re.findall(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", row):
                row = row.replace(
                    "{{" + token + "}}",
                    get_nested_demo_value(item, token),
                )

            rows.append(row.strip())

        return "\n".join(row for row in rows if row)

    return pattern.sub(replace_block, prompt)


def render_first_demo_item_variables(prompt: str, items: list[dict]) -> str:
    if not items:
        return prompt

    first_item = items[0]
    message = prompt

    for token in re.findall(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", message):
        value = get_nested_demo_value(first_item, token)

        if value != "":
            message = message.replace("{{" + token + "}}", value)

    return message


def summarize_demo_condition(result: dict, limit: int = 5) -> str:
    if not result.get("matched"):
        return ""

    title = (
        result.get("template_name")
        or result.get("condition")
        or result.get("condition_key")
        or "Dieu kien"
    )
    items = extract_demo_items(result)

    if items:
        visible = items[:limit]
        extra = len(items) - len(visible)
        suffix = ", ".join(visible)

        if extra > 0:
            suffix = f"{suffix} (+{extra})"

        return f"- {title}: {suffix}"

    message = result.get("message")

    if message:
        return f"- {title}: {message}"

    return f"- {title}"


def render_demo_trigger_prompt(
    prompt: str,
    flow_name: str,
    condition_results: list[dict],
    check_date: str | None = None,
) -> str:
    matched_results = [
        result for result in condition_results
        if result.get("matched")
    ]
    condition_names = [
        str(
            result.get("template_name")
            or result.get("condition")
            or result.get("condition_key")
            or ""
        )
        for result in matched_results
    ]
    condition_names = [name for name in condition_names if name]
    messages = [
        str(result.get("message") or "")
        for result in matched_results
    ]
    messages = [message for message in messages if message]
    items = []
    raw_items = []

    for result in matched_results:
        for item in extract_demo_items(result):
            if item not in items:
                items.append(item)
        raw_items.extend(extract_demo_raw_items(result))

    visible_items = items[:5]
    item_details = []

    for result in matched_results:
        for detail in extract_demo_item_details(result):
            if detail not in item_details:
                item_details.append(detail)

    visible_item_details = item_details[:5]
    extra_count = max(0, len(items) - len(visible_items))

    replacements = {
        "flow_name": flow_name,
        "condition_name": condition_names[0] if condition_names else "",
        "condition_names": ", ".join(condition_names),
        "items": ", ".join(visible_items),
        "items_detail": "; ".join(visible_item_details),
        "total": str(len(items)),
        "extra_count": str(extra_count),
        "message": "\n".join(messages),
        "date": check_date or "",
    }

    message = render_demo_item_blocks(prompt, raw_items)
    message = render_first_demo_item_variables(message, raw_items)

    for key, value in replacements.items():
        message = message.replace("{{" + key + "}}", value)

    return message.strip()


def build_demo_flow_message(
    flow_name: str,
    condition_results: list[dict],
    trigger_prompt: str | None = None,
    check_date: str | None = None,
) -> str:
    if trigger_prompt and trigger_prompt.strip():
        return render_demo_trigger_prompt(
            trigger_prompt.strip(),
            flow_name,
            condition_results,
            check_date,
        )

    lines = [flow_name]
    summaries = [
        summary for summary in (
            summarize_demo_condition(result)
            for result in condition_results
        )
        if summary
    ]

    if summaries:
        lines.extend(["", "Mau da thoa dieu kien:"])
        lines.extend(summaries)

    return "\n".join(lines)


def build_demo_flow_ai_messages(
    flow_name: str,
    condition_results: list[dict],
    trigger_prompt: str,
    check_date: str | None = None,
) -> list[dict]:
    matched_results = [
        result for result in condition_results
        if result.get("matched")
    ]
    summaries = [
        summary for summary in (
            summarize_demo_condition(result, limit=8)
            for result in matched_results
        )
        if summary
    ]
    item_details = []

    for result in matched_results:
        for detail in extract_demo_item_details(result):
            if detail not in item_details:
                item_details.append(detail)

    raw_preview = []
    for result in matched_results:
        for item in extract_demo_raw_items(result):
            if len(raw_preview) >= 12:
                break
            raw_preview.append(item)

    context = {
        "flow_name": flow_name,
        "check_date": check_date or "",
        "matched_conditions": summaries,
        "matched_item_details": item_details[:12],
        "raw_preview": raw_preview,
    }

    return [
        {
            "role": "system",
            "content": (
                "Bạn là trợ lý StockTraders AI viết một câu chào mở đầu trong khung chat khi khách vừa vào web. "
                "Đây không phải email, không phải bản tin, không phải khuyến nghị đầu tư dài. "
                "Chỉ viết 1-2 câu ngắn, tự nhiên, thân thiện, như một nhân viên tư vấn mở lời. "
                "Chọn đúng 1 mã/ngành/tín hiệu nổi bật nhất để nói, không liệt kê nhiều kết quả. "
                "Không dùng các cụm kiểu 'Kính chào quý khách', 'Chúng tôi muốn thông báo', 'Trân trọng', 'vui lòng liên hệ'. "
                "Không xuống dòng chữ ký. Không markdown. Không tự thêm lời khuyên mua/bán. "
                "Nếu nhắc chỉ số SMDT, luôn viết kèm ký hiệu % sau số, ví dụ 72.5%. "
                "Dựa đúng dữ liệu được cung cấp, không bịa mã/ngành/số liệu. Nếu có nhiều kết quả, hãy tự chọn một dòng đáng chú ý nhất dựa trên mức tăng, độ rõ của tín hiệu, hoặc item đầu tiên nếu dữ liệu không đủ để xếp hạng. "
                "Nếu prompt của admin chỉ nêu ý tưởng, hãy diễn đạt lại thành câu chào dễ hiểu."
            ),
        },
        {
            "role": "user",
            "content": (
                "Ý tưởng/prompt của admin:\n"
                f"{trigger_prompt.strip()}\n\n"
                "Dữ liệu điều kiện đã thỏa:\n"
                f"{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
                "Hãy viết một câu chào ngắn để bot mở đầu cuộc chat với khách, chỉ nói về 1 tín hiệu nổi bật nhất."
            ),
        },
    ]


def cashflow_branch_rows(raw):
    rows = []

    if isinstance(raw, dict):
        rows = raw.get("cashFlowBranchs") or raw.get("data") or []
    elif isinstance(raw, list):
        rows = raw

    return rows if isinstance(rows, list) else []


def branch_cashflow_items(raw):
    items = []

    for row in cashflow_branch_rows(raw):
        if not isinstance(row, dict):
            continue

        data = row.get("cashFlowBranchDatas") or row.get("items") or []

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    items.append({
                        **item,
                        "date": item.get("date") or row.get("date"),
                    })

    return items


def cashflow_is_in(item: dict) -> bool:
    content = normalize_condition_text(
        " ".join([
            str(item.get("content") or ""),
            str(item.get("value") or ""),
            str(item.get("cashflow") or ""),
            str(item.get("cashFlow") or ""),
        ])
    )

    return (
        re.search(r"\b2\b", content) is not None
        or "do vao" in content
        or "vao" in content
    )


async def condition_core_branch_smdt_cross_70_cashflow_in(context: dict):
    date = context.get("date")

    if not date:
        return {
            "ok": False,
            "matched": False,
            "condition_key": "core_branch_smdt_cross_70_cashflow_in",
            "message": "Thieu date de kiem tra nganh chu luc va dong tien",
        }

    raw = await post_data_api(
        "getCoreBranchLeader",
        {"date": date},
    )

    if is_api_error(raw):
        return {
            "ok": False,
            "matched": False,
            "condition_key": "core_branch_smdt_cross_70_cashflow_in",
            "message": raw["message"],
            "error": raw,
        }

    branches = []

    if isinstance(raw, dict):
        branches = raw.get("branches") or []

    matches = []

    for branch in branches:
        if not isinstance(branch, dict):
            continue

        cashflow_params = {"date": date}
        branch_name = branch.get("name") or branch.get("keyName")
        branch_path = branch.get("path") or branch.get("keyValue")

        if branch_path:
            cashflow_params["path"] = branch_path
        elif branch_name:
            cashflow_params["name"] = branch_name

        cashflow_raw = await post_data_api(
            "getCashFlowBranch",
            cashflow_params,
        )

        if is_api_error(cashflow_raw):
            continue

        cashflow_items = branch_cashflow_items(cashflow_raw)
        matched_cashflow = next(
            (
                item for item in cashflow_items
                if cashflow_is_in(item)
            ),
            None,
        )

        if matched_cashflow:
            matches.append({
                "branch": branch_name or matched_cashflow.get("name") or "",
                "path": branch_path or matched_cashflow.get("path") or "",
                "date": matched_cashflow.get("date") or date,
                "cashflow": matched_cashflow.get("content") or "",
                "points": branch.get("points") or branch.get("smdts") or [],
            })

    return {
        "ok": True,
        "matched": len(matches) > 0,
        "condition_key": "core_branch_smdt_cross_70_cashflow_in",
        "condition": "SMDT Nganh chu luc vuot 70 va co tien do vao",
        "count": len(matches),
        "data": matches,
        "message": (
            "Co nganh chu luc vuot 70 va co tien do vao"
            if matches
            else "Khong co nganh chu luc vuot 70 va co tien do vao"
        ),
    }


async def condition_smdt_branch_up_3_sessions(context: dict):
    date = context.get("date")
    params = {}

    if date:
        params["date"] = date[:7] if len(str(date)) >= 7 else date

    if context.get("keyName"):
        params["keyName"] = context.get("keyName")
    elif context.get("branch"):
        params["keyName"] = context.get("branch")

    if context.get("path"):
        params["path"] = context.get("path")

    raw = await post_data_api(
        "getSMDTBranch",
        params,
    )

    if is_api_error(raw):
        return {
            "ok": False,
            "matched": False,
            "condition_key": "smdt_branch_up_3_sessions",
            "message": raw["message"],
            "error": raw,
        }

    matches = []

    for branch in get_smdt_branch_rows(raw):
        if not isinstance(branch, dict):
            continue

        recent = get_recent_branch_smdt_points(branch, date)

        if len(recent) < 3:
            continue

        first, second, third = recent

        if third["smdt"] > second["smdt"] > first["smdt"]:
            matches.append({
                "branch": (
                    branch.get("keyName")
                    or branch.get("name")
                    or branch.get("branch")
                    or ""
                ),
                "path": branch.get("keyValue") or branch.get("path") or "",
                "dates": [point["date"] for point in recent],
                "smdt_last3": [point["smdt"] for point in recent],
            })

    return {
        "ok": True,
        "matched": len(matches) > 0,
        "condition_key": "smdt_branch_up_3_sessions",
        "condition": "SMDT Nganh tang 3 phien lien tiep",
        "count": len(matches),
        "data": matches,
        "message": (
            "Co nganh SMDT tang 3 phien lien tiep"
            if matches
            else "Khong co nganh SMDT tang 3 phien lien tiep"
        ),
    }

async def run_condition(template_id: int, context: dict):
    condition_key = resolve_condition_key(context.get("condition_key"))

    if condition_key == "waitbuy_over_200":
        return await condition_waitbuy_over_200(context)

    if condition_key == "vnindex_down_10_waitbuy_reversal":
        return await condition_vnindex_down_10_waitbuy_reversal(context)

    if condition_key == "core_branch_smdt_cross_70":
        return await condition_core_branch_smdt_cross_70(context)

    if condition_key == "core_branch_smdt_cross_70_cashflow_in":
        return await condition_core_branch_smdt_cross_70_cashflow_in(context)

    if condition_key == "smdt_ticker_cross_70_prev_up":
        return await condition_smdt_ticker_cross_70_prev_up(context)

    if condition_key == "smdt_up_3_sessions":
        return await condition_smdt_up_3_sessions(context)

    if condition_key == "smdt_branch_up_3_sessions":
        return await condition_smdt_branch_up_3_sessions(context)

    return {
        "ok": False,
        "matched": False,
        "message": "Chưa hỗ trợ condition_key này",
        "condition_key": condition_key,
    }

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

from services.branch_tickers import BRANCH_DATA
from services.ticker_policy import ALLOWED_TICKERS, normalize_ticker


class Stock4KeyError(Exception):
    pass


@dataclass(frozen=True)
class SmdtPoint:
    date: str
    smdt: float


@dataclass(frozen=True)
class PricePoint:
    date: str
    close: float


@dataclass(frozen=True)
class CashFlowPoint:
    date: str
    value: Optional[float] = None
    content: Optional[str] = None


WEIGHTS_V2 = {
    "smdt_vs_nganh": 32.0,
    "smdt_delta": 30.0,
    "smdt_rank": 18.0,
    "gia_dong_luong": 10.0,
    "dong_tien": 10.0,
}
MAX_DIVERGENCE_BONUS = 8.0
PRICE_FLAT_THRESHOLD = 0.005
FOUR_KEY_HISTORY_BUFFER_DAYS = 30
COMPOSITE_HISTORY_BUFFER_DAYS = 45
CASHFLOW_SCORE_MAP = {
    "Tiếp tục đổ vào": 1.0,
    "Đang đổ vào": 1.0,
    "Nhen nhóm đổ vào": 0.5,
    "Tiếp tục thoát ra": -1.0,
    "Đang thoát ra": -1.0,
    "Bắt đầu thoát ra": -0.5,
}



def _year_from_date(value: Optional[str]) -> int:
    if value and re.match(r"^20\d{2}", str(value)):
        return int(str(value)[:4])
    return date.today().year


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _dedupe_smdt(points: Iterable[SmdtPoint]) -> list[SmdtPoint]:
    by_date: dict[str, SmdtPoint] = {}
    for point in points:
        if point.date:
            by_date[point.date] = point
    return [by_date[key] for key in sorted(by_date)]


def _dedupe_price(points: Iterable[PricePoint]) -> list[PricePoint]:
    by_date: dict[str, PricePoint] = {}
    for point in points:
        if point.date:
            by_date[point.date] = point
    return [by_date[key] for key in sorted(by_date)]


def _dedupe_cashflow(points: Iterable[CashFlowPoint]) -> list[CashFlowPoint]:
    by_date: dict[str, CashFlowPoint] = {}
    for point in points:
        if point.date:
            by_date[point.date] = point
    return [by_date[key] for key in sorted(by_date)]


def extract_smdt_points(payload: Any) -> list[SmdtPoint]:
    points: list[SmdtPoint] = []
    for item in _walk(payload):
        if isinstance(item, dict) and "date" in item and "smdt" in item:
            value = _to_float(item.get("smdt"))
            if value is not None:
                points.append(SmdtPoint(str(item.get("date"))[:10], value))
    return _dedupe_smdt(points)


def extract_price_points(payload: Any) -> list[PricePoint]:
    points: list[PricePoint] = []
    for item in _walk(payload):
        if not isinstance(item, dict) or "date" not in item:
            continue
        close = _to_float(item.get("close") or item.get("price") or item.get("c"))
        if close is not None:
            points.append(PricePoint(str(item.get("date"))[:10], close))
    return _dedupe_price(points)


def extract_cashflow_points(payload: Any) -> list[CashFlowPoint]:
    points: list[CashFlowPoint] = []
    for item in _walk(payload):
        if not isinstance(item, dict) or "date" not in item:
            continue
        value = _to_float(item.get("value") or item.get("val") or item.get("score"))
        content = item.get("content") or item.get("cashflow") or item.get("cashFlow")
        if value is not None or content:
            points.append(CashFlowPoint(str(item.get("date"))[:10], value, str(content).strip() if content else None))
    return _dedupe_cashflow(points)


def find_branch_for_ticker(ticker: str) -> Optional[dict[str, Any]]:
    ticker = normalize_ticker(ticker)
    for branch in BRANCH_DATA:
        if ticker in {normalize_ticker(item) for item in branch.get("tickers", [])}:
            return branch
    return None


def extract_branch_from_payload(payload: Any, ticker: str) -> Optional[dict[str, Any]]:
    ticker = normalize_ticker(ticker)
    for item in _walk(payload):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        tickers = item.get("tickers") or []
        if isinstance(tickers, str):
            ticker_values = {normalize_ticker(value) for value in re.split(r"[\s,;]+", tickers)}
        else:
            ticker_values = {normalize_ticker(value) for value in tickers}
        if ticker_values and ticker not in ticker_values:
            continue
        return {
            "name": item.get("name") or item.get("keyName") or path,
            "path": path,
            "tickers": sorted(ticker_values) if ticker_values else [ticker],
        }
    return None


def _pick_target_date(
    ticker_points: list[SmdtPoint],
    branch_points: list[SmdtPoint],
    requested_date: Optional[str],
) -> str:
    ticker_dates = {point.date for point in ticker_points}
    branch_dates = {point.date for point in branch_points}
    common = sorted(ticker_dates & branch_dates)
    if not common:
        raise Stock4KeyError("Khong co ngay SMDT chung giua ma va nganh")

    if not requested_date:
        raise Stock4KeyError("Thieu ngay danh gia")
    target = requested_date[:10]
    if target not in common:
        raise Stock4KeyError(f"Khong co du lieu SMDT chung cua ma va nganh ngay {target}")
    return target


def _point_index(points: list[SmdtPoint], target: str) -> int:
    for idx, point in enumerate(points):
        if point.date == target:
            return idx
    raise Stock4KeyError(f"Khong co du lieu SMDT ngay {target}")


def _price_index(points: list[PricePoint], target: str) -> Optional[int]:
    for idx, point in enumerate(points):
        if point.date == target:
            return idx
    return None


def _cashflow_for_date(points: list[CashFlowPoint], target: str) -> Optional[CashFlowPoint]:
    eligible = [point for point in points if point.date <= target]
    return eligible[-1] if eligible else None


def _group(delta_ticker: float, delta_branch: float) -> tuple[str, str]:
    right_wave = delta_ticker > 0
    right_branch = delta_branch > 0
    if right_wave and right_branch:
        return "Dung song - Dung nganh", "MUA - tin hieu thuan ca ma va nganh"
    if right_wave and not right_branch:
        return "Dung song - Sai nganh", "CAN NHAC - ma manh rieng, nguoc dong nganh"
    if not right_wave and right_branch:
        return "Dung nganh - Sai song", "THEO DOI - nganh thuan nhung ma chua xac nhan"
    return "Sai song - Sai nganh", "TRANH - ca ma va nganh deu bat loi"


def _normalize_series(values: list[float]) -> list[float]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return [50.0 for _ in values]
    return [((value - lo) / (hi - lo)) * 100.0 for value in values]


def _cashflow_score(point: Optional[CashFlowPoint], notes: list[str]) -> float:
    if point is None:
        notes.append("Thieu du lieu dong tien, tinh trung lap 50 diem")
        return 50.0
    if point.content:
        mapped = CASHFLOW_SCORE_MAP.get(point.content)
        if mapped is not None:
            return (mapped + 1.0) / 2.0 * 100.0
        notes.append(f"Tin hieu dong tien '{point.content}' chua co trong bang diem, tinh trung lap 50 diem")
        return 50.0
    value = point.value
    if value is None:
        notes.append("Thieu du lieu dong tien, tinh trung lap 50 diem")
        return 50.0
    if -1.0 <= value <= 1.0:
        return (value + 1.0) / 2.0 * 100.0
    if 0.0 <= value <= 100.0:
        return value
    return max(0.0, min(100.0, (value + 100.0) / 200.0 * 100.0))


def evaluate_four_key_from_records(
    ticker: str,
    branch_name: str,
    ticker_smdt: list[SmdtPoint],
    branch_smdt: list[SmdtPoint],
    requested_date: Optional[str] = None,
    lookback_sessions: int = 3,
    price_points: Optional[list[PricePoint]] = None,
    cashflow_points: Optional[list[CashFlowPoint]] = None,
    include_composite: bool = True,
) -> dict[str, Any]:
    ticker = normalize_ticker(ticker)
    ticker_smdt = _dedupe_smdt(ticker_smdt)
    branch_smdt = _dedupe_smdt(branch_smdt)
    price_points = _dedupe_price(price_points or [])
    cashflow_points = _dedupe_cashflow(cashflow_points or [])

    target = _pick_target_date(ticker_smdt, branch_smdt, requested_date)
    ticker_idx = _point_index(ticker_smdt, target)
    branch_idx = _point_index(branch_smdt, target)
    if ticker_idx < lookback_sessions or branch_idx < lookback_sessions:
        raise Stock4KeyError(f"Khong du {lookback_sessions} phien lich su truoc {target}")

    smdt_ticker_now = ticker_smdt[ticker_idx].smdt
    smdt_ticker_prev = ticker_smdt[ticker_idx - lookback_sessions].smdt
    smdt_branch_now = branch_smdt[branch_idx].smdt
    smdt_branch_prev = branch_smdt[branch_idx - lookback_sessions].smdt
    delta_ticker = smdt_ticker_now - smdt_ticker_prev
    delta_branch = smdt_branch_now - smdt_branch_prev
    group, recommendation = _group(delta_ticker, delta_branch)

    result: dict[str, Any] = {
        "ok": True,
        "ticker": ticker,
        "branch": branch_name,
        "requested_date": requested_date,
        "date": target,
        "lookback_sessions": lookback_sessions,
        "group_4key": group,
        "recommendation": recommendation,
        "smdt_ticker": round(smdt_ticker_now, 2),
        "smdt_ticker_prev": round(smdt_ticker_prev, 2),
        "ticker_momentum": round(delta_ticker, 2),
        "smdt_branch": round(smdt_branch_now, 2),
        "smdt_branch_prev": round(smdt_branch_prev, 2),
        "branch_momentum": round(delta_branch, 2),
    }

    if include_composite:
        result["composite"] = _composite_score(
            target=target,
            ticker_smdt=ticker_smdt,
            branch_smdt=branch_smdt,
            price_points=price_points,
            cashflow_points=cashflow_points,
            lookback_sessions=lookback_sessions,
        )
    return result


def _composite_score(
    target: str,
    ticker_smdt: list[SmdtPoint],
    branch_smdt: list[SmdtPoint],
    price_points: list[PricePoint],
    cashflow_points: list[CashFlowPoint],
    lookback_sessions: int,
) -> dict[str, Any]:
    notes: list[str] = []
    branch_by_date = {point.date: point.smdt for point in branch_smdt}
    rows: list[dict[str, float | str]] = []
    for idx, point in enumerate(ticker_smdt):
        if point.date not in branch_by_date:
            continue
        delta = 0.0
        if idx >= lookback_sessions:
            delta = point.smdt - ticker_smdt[idx - lookback_sessions].smdt
        rows.append({
            "date": point.date,
            "smdt_vs_nganh": point.smdt - branch_by_date[point.date],
            "smdt_delta": delta,
        })
    if not rows or target not in {str(row["date"]) for row in rows}:
        raise Stock4KeyError("Khong du du lieu de tinh composite score")

    vs_scores = _normalize_series([float(row["smdt_vs_nganh"]) for row in rows])
    delta_scores = _normalize_series([float(row["smdt_delta"]) for row in rows])
    for idx, row in enumerate(rows):
        row["score_smdt_vs_nganh"] = vs_scores[idx]
        row["score_smdt_delta"] = delta_scores[idx]
    row = next(item for item in rows if item["date"] == target)

    active_weights = dict(WEIGHTS_V2)
    active_weights.pop("smdt_rank", None)
    notes.append("Chua co du lieu peer ranking trong adapter, bo factor smdt_rank")

    breakdown = {
        "smdt_vs_nganh": round(float(row["score_smdt_vs_nganh"]), 1),
        "smdt_delta": round(float(row["score_smdt_delta"]), 1),
    }
    weighted_sum = (
        active_weights["smdt_vs_nganh"] * float(row["score_smdt_vs_nganh"])
        + active_weights["smdt_delta"] * float(row["score_smdt_delta"])
    )

    price_idx = _price_index(price_points, target)
    bonus = 0.0
    has_divergence = False
    if price_idx is None or price_idx == 0:
        active_weights.pop("gia_dong_luong", None)
        notes.append("Thieu du lieu gia dung ngay muc tieu, bo factor gia va bonus phan ky")
    else:
        one_day_return = (price_points[price_idx].close / price_points[price_idx - 1].close) - 1.0
        returns = []
        for idx in range(1, len(price_points)):
            prev = price_points[idx - 1].close
            returns.append((price_points[idx].close / prev) - 1.0 if prev else 0.0)
        price_scores = _normalize_series(returns)
        price_score = price_scores[max(0, price_idx - 1)] if price_scores else 50.0
        weighted_sum += active_weights["gia_dong_luong"] * price_score
        breakdown["gia_dong_luong"] = round(price_score, 1)

        smdt_delta = float(row["smdt_delta"])
        if price_idx >= lookback_sessions:
            base_close = price_points[price_idx - lookback_sessions].close
            price_lookback_return = (price_points[price_idx].close / base_close) - 1.0 if base_close else 0.0
            if smdt_delta > 0 and price_lookback_return <= PRICE_FLAT_THRESHOLD:
                has_divergence = True
                max_delta = max([abs(float(item["smdt_delta"])) for item in rows] or [1.0]) or 1.0
                bonus = round(min(smdt_delta / max_delta, 1.0) * MAX_DIVERGENCE_BONUS, 1)
                notes.append(
                    f"Phat hien phan ky: SMDT tang {smdt_delta:.2f} nhung gia {lookback_sessions} phien la {price_lookback_return * 100:.2f}%"
                )
        breakdown["gia_return_1d_pct"] = round(one_day_return * 100.0, 2)

    cashflow = _cashflow_for_date(cashflow_points, target)
    cash_score = _cashflow_score(cashflow, notes)
    weighted_sum += active_weights["dong_tien"] * cash_score
    breakdown["dong_tien"] = round(cash_score, 1)

    total_weight = sum(active_weights.values())
    score = max(0.0, min(100.0, weighted_sum / total_weight + bonus)) if total_weight else 0.0
    return {
        "score": round(score, 1),
        "rating": _rating(score),
        "bonus_phan_ky": bonus,
        "co_phan_ky": has_divergence,
        "breakdown": breakdown,
        "notes": notes,
    }


def _rating(score: float) -> str:
    if score >= 70:
        return "Mua manh"
    if score >= 55:
        return "Mua"
    if score >= 45:
        return "Trung lap"
    if score >= 30:
        return "Ban"
    return "Ban manh"


def _merge_records(first: list[Any], second: list[Any]) -> list[Any]:
    by_date = {getattr(item, "date"): item for item in first + second if getattr(item, "date", None)}
    return [by_date[key] for key in sorted(by_date)]


def _month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    month_index = (year * 12) + (month - 1) + delta
    return month_index // 12, (month_index % 12) + 1


def _month_filter(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _month_filters_for_target(value: Optional[str]) -> list[str]:
    raw = str(value or "").strip()
    if re.match(r"^20\d{2}-\d{2}-\d{2}$", raw):
        dt = datetime.strptime(raw, "%Y-%m-%d")
        prev_year, prev_month = _month_shift(dt.year, dt.month, -1)
        return [_month_filter(prev_year, prev_month), _month_filter(dt.year, dt.month)]
    if re.match(r"^20\d{2}-\d{2}$", raw):
        year, month = int(raw[:4]), int(raw[5:7])
        prev_year, prev_month = _month_shift(year, month, -1)
        return [_month_filter(prev_year, prev_month), _month_filter(year, month)]
    if re.match(r"^20\d{2}$", raw):
        year = int(raw)
        today = date.today()
        month = today.month if year == today.year else 12
        prev_year, prev_month = _month_shift(year, month, -1)
        return [_month_filter(prev_year, prev_month), _month_filter(year, month)]
    return []


def _month_filters_between(start: str, end: str) -> list[str]:
    start_dt = datetime.strptime(start[:10], "%Y-%m-%d")
    end_dt = datetime.strptime(end[:10], "%Y-%m-%d")
    year, month = start_dt.year, start_dt.month
    values: list[str] = []
    while (year, month) <= (end_dt.year, end_dt.month):
        values.append(_month_filter(year, month))
        year, month = _month_shift(year, month, 1)
    return values


def _fetch_months(api_call: Callable[[str, dict[str, Any]], Any], operation: str, base_args: dict[str, Any], months: list[str]) -> list[Any]:
    payloads = []
    for value in dict.fromkeys(months):
        args = dict(base_args)
        args["date"] = value
        payloads.append(api_call(operation, args))
    return payloads


def _fetch_smdt_last_n(
    api_call: Callable[[str, dict[str, Any]], Any],
    *,
    n: int,
    ticker: Optional[str] = None,
    path: Optional[str] = None,
) -> list[SmdtPoint]:
    args: dict[str, Any] = {"n": n}
    if ticker:
        args["ticker"] = ticker
    if path:
        args["path"] = path
    return extract_smdt_points(api_call("getSMDTLastN", args))


def _filter_smdt_range(points: list[SmdtPoint], start: str, end: str) -> list[SmdtPoint]:
    return [point for point in _dedupe_smdt(points) if start <= point.date <= end]


def _filter_price_range(points: list[PricePoint], start: str, end: str) -> list[PricePoint]:
    return [point for point in _dedupe_price(points) if start <= point.date <= end]


def _load_inputs(
    api_call: Callable[[str, dict[str, Any]], Any],
    ticker: str,
    requested_date: Optional[str],
    history_buffer_days: int,
) -> tuple[str, list[SmdtPoint], list[SmdtPoint], list[PricePoint], list[CashFlowPoint]]:
    if not requested_date:
        raise Stock4KeyError("Thieu ngay danh gia")

    ticker = normalize_ticker(ticker)
    if ticker not in ALLOWED_TICKERS:
        raise Stock4KeyError("Ticker khong nam trong whitelist")
    branch = find_branch_for_ticker(ticker)
    if not branch:
        branch = extract_branch_from_payload(api_call("getBranchPath", {"ticker": ticker}), ticker)
    if not branch:
        raise Stock4KeyError(f"Chua co mapping nganh cho {ticker}")

    target = requested_date[:10]
    target_dt = datetime.strptime(target, "%Y-%m-%d")
    from_date = (target_dt - timedelta(days=history_buffer_days)).strftime("%Y-%m-%d")
    months = _month_filters_between(from_date, target)

    branch_name = str(branch.get("name") or branch.get("path") or "")
    branch_path = branch.get("path")

    ticker_smdt = _fetch_smdt_last_n(
        api_call,
        n=history_buffer_days,
        ticker=ticker,
    )
    ticker_smdt = _filter_smdt_range(ticker_smdt, from_date, target)

    branch_smdt = _fetch_smdt_last_n(
        api_call,
        n=history_buffer_days,
        path=branch_path,
    )
    branch_smdt = _filter_smdt_range(branch_smdt, from_date, target)

    price_payload = api_call("getTotalTrade", {"ticker": ticker, "lastDates": history_buffer_days})
    prices = extract_price_points(price_payload)
    if target == date.today().isoformat():
        real_price_payload = api_call("getTotalTradeReal", {"ticker": ticker})
        prices = _merge_records(prices, extract_price_points(real_price_payload))
    prices = _filter_price_range(prices, from_date, target)

    cash_payload = api_call("getCashFlowTicker", {"ticker": ticker, "date": target})
    cashflows = extract_cashflow_points(cash_payload)
    return branch_name, ticker_smdt, branch_smdt, prices, cashflows

def evaluate_stock_4key(
    api_call: Callable[[str, dict[str, Any]], Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    mode = str(args.get("mode") or "single").strip().lower()
    requested_date = str(args.get("date") or "").strip() or None
    from_date = str(args.get("from_date") or "").strip() or None
    lookback = int(args.get("lookback_sessions") or 3)
    include_composite = bool(args.get("include_composite", True))

    if mode == "batch":
        if not requested_date:
            raise Stock4KeyError("Thieu ngay danh gia")
        raw_tickers = args.get("tickers") or args.get("ticker") or []
        if isinstance(raw_tickers, str):
            tickers = [item for item in re.split(r"[\s,;]+", raw_tickers.upper()) if item]
        else:
            tickers = [normalize_ticker(item) for item in raw_tickers]
        results = []
        for ticker in tickers[:30]:
            try:
                branch_name, ticker_smdt, branch_smdt, prices, cashflows = _load_inputs(
                    api_call,
                    ticker,
                    requested_date,
                    FOUR_KEY_HISTORY_BUFFER_DAYS,
                )
                results.append(evaluate_four_key_from_records(
                    ticker=ticker,
                    branch_name=branch_name,
                    ticker_smdt=ticker_smdt,
                    branch_smdt=branch_smdt,
                    requested_date=requested_date,
                    lookback_sessions=lookback,
                    price_points=prices,
                    cashflow_points=cashflows,
                    include_composite=False,
                ))
            except Exception as exc:
                results.append({"ok": False, "ticker": ticker, "error": str(exc)})
        return {"ok": True, "mode": "batch", "results": results}

    ticker = normalize_ticker(args.get("ticker"))
    if not ticker:
        raise Stock4KeyError("Thieu ticker")

    if mode == "history":
        if not from_date:
            raise Stock4KeyError("Thieu from_date cho mode history")
        end_date = date.today().isoformat()
        branch_name, ticker_smdt, branch_smdt, prices, cashflows = _load_inputs(
            api_call,
            ticker,
            end_date,
            FOUR_KEY_HISTORY_BUFFER_DAYS,
        )
        # FourKeyEvaluator.evaluate_history in the source module returns 4-key history only.
        common_dates = sorted({p.date for p in ticker_smdt} & {p.date for p in branch_smdt})
        results = []
        for value in common_dates:
            if value < from_date[:10]:
                continue
            try:
                results.append(evaluate_four_key_from_records(
                    ticker=ticker,
                    branch_name=branch_name,
                    ticker_smdt=ticker_smdt,
                    branch_smdt=branch_smdt,
                    requested_date=value,
                    lookback_sessions=lookback,
                    price_points=prices,
                    cashflow_points=cashflows,
                    include_composite=False,
                ))
            except Stock4KeyError:
                continue
        return {"ok": True, "mode": "history", "ticker": ticker, "from_date": from_date, "results": results}

    if not requested_date:
        raise Stock4KeyError("Thieu ngay danh gia")
    history_buffer_days = COMPOSITE_HISTORY_BUFFER_DAYS if include_composite else FOUR_KEY_HISTORY_BUFFER_DAYS
    branch_name, ticker_smdt, branch_smdt, prices, cashflows = _load_inputs(
        api_call,
        ticker,
        requested_date,
        history_buffer_days,
    )
    result = evaluate_four_key_from_records(
        ticker=ticker,
        branch_name=branch_name,
        ticker_smdt=ticker_smdt,
        branch_smdt=branch_smdt,
        requested_date=requested_date,
        lookback_sessions=lookback,
        price_points=prices,
        cashflow_points=cashflows,
        include_composite=include_composite,
    )
    result["mode"] = "single"
    return result
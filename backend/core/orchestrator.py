import asyncio
import json
import re
import unicodedata
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime

from core.prompt import SYSTEM_PROMPT
from core.model_router import pick_model
from core.memory import MemoryStore
from core.rag import RAGStore
from core.tool_engine import ToolRegistry
from core.condition_engine import extract_rows, scan_vnindex_waitbuy_reversal
from core.question_guide import QuestionGuide, extract_date_value

from services.api_executor import APIExecutor
from services.openai_client import OpenAIClient, current_token_usage, reset_token_usage
from services.ticker_policy import (
    ALLOWED_TICKERS,
    MARKET_INDEX_TICKERS,
    allowed_tickers_text,
    find_disallowed_tickers,
    sanitize_response_text,
)
from settings import MAX_TOOL_LOOPS, CLASSIFIER_MODEL
from core.constants import MAIN_BRANCHES, MAIN_BRANCH_ALIASES

STREAM_CHUNK_CHARS = 60

# =====================================================
# DEBUG
# =====================================================

DEBUG = True

def log(*args):
    if DEBUG:
        print(*args)

# =====================================================
# STOCK ROUTER
# =====================================================

STOCK_KEYWORDS = [
    "giá","cổ phiếu","smdt","ngành","mã","tín hiệu", "suy yếu", "lộ trình", "thống kê",
    "chứng khoán","dòng tiền","sentiment","chân sóng","sóng", "chờ mua", "chờ bán", "mua", "bán", "độ tin cậy"
]

MAIN_BRANCH_KEYWORDS = [ "chủ lực", "chu luc", "ngành mạnh", "nganh manh", "dẫn sóng", "dan song"]

def need_main_branches(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in MAIN_BRANCH_KEYWORDS)

def enforce_main_branch_terms(text: str) -> str:
    fixed = text or ""
    fixed_l = fixed.lower()

    mentions_main_branch = any(branch.lower() in fixed_l for branch in MAIN_BRANCHES)
    mentions_alias = any(alias.lower() in fixed_l for alias in MAIN_BRANCH_ALIASES)

    if mentions_main_branch or mentions_alias:
        fixed = fixed.replace("ngành phụ", "ngành chủ lực")
        fixed = fixed.replace("Ngành phụ", "Ngành chủ lực")

    return fixed

TICKER_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,4}\b")
NON_TICKER_SYMBOLS = frozenset({"RSI", "NAV", "SMDT", "GPT", "AI", "API", "MACD"})
NORMALIZED_STOCK_KEYWORDS = (
    "gia", "co phieu", "smdt", "nganh", "ma", "tin hieu", "suy yeu",
    "lo trinh", "thong ke", "chung khoan", "dong tien", "sentiment",
    "chan song", "song", "cho mua", "cho ban", "mua", "ban", "do tin cay", "key nao", "key gi", "co key gi", "thuoc key", "nhom nao", "danh gia", "trang thai", "phan tich", "4 key", "four key", "dung song", "dung nganh", "composite score",
)
FORCE_RULES_PHRASES = (
    "phan tich nganh", "phan tich co phieu", "phan tich ma", "smdt co phieu",
    "smdt nganh", "dong tien", "cho mua", "cho ban", "tin hieu",
    "nganh nao", "ma nao", "gia co phieu", "gia hom nay", "vuot", "cross",
    "dat chuan ma manh", "ma manh", "bat dau manh", "dan song", "chan song", "key nao", "key gi", "co key gi", "thuoc key", "nhom nao", "danh gia", "trang thai", "phan tich", "4 key", "four key", "dung song", "dung nganh", "composite score",
)
SMDT_DATA_INTENT_WORDS = (
    "hom nay", "ngay", "co phieu", "ma", "nganh", "bao nhieu", "tang",
    "giam", "vuot", "cross", "phien",
)
DEFINITION_INTENT_PHRASES = (
    "la gi", "nghia la gi", "khai niem", "dinh nghia", "hieu the nao",
    "nen hieu the nao",
)
DATA_INTENT_PHRASES = (
    "hom nay", "ngay", "thang", "nam", "bao nhieu", "thong ke",
    "phan tich", "tang", "giam", "vuot", "cross", "phien",
)


def normalize_search_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = normalized.replace("đ", "d").replace("Đ", "D")
    normalized = normalized.lower()
    return re.sub(r"\s+", " ", normalized).strip()


def ensure_smdt_percent(text: str) -> str:
    if "smdt" not in normalize_search_text(text):
        return text or ""

    text = re.sub(r"(\d+)%([.,])(\d+)%", r"\1\2\3%", text or "")

    def should_skip(match: re.Match) -> bool:
        raw = match.group(0)
        start, end = match.span()
        after = (text[end:end + 24] or "").lower()
        before = (text[max(0, start - 24):start] or "").lower()
        local_context = normalize_search_text(before + raw + after)

        # Only format a number that is locally associated with the SMDT metric.
        if "smdt" not in local_context:
            return True
        if after.lstrip().startswith("%"):
            return True
        # Ordered-list markers such as "10. BCM" are not SMDT values.
        if re.match(r"\s*[.)]\s+\S", after):
            return True
        if after.lstrip().startswith(("/", "-")) or before.rstrip().endswith(("/", "-")):
            return True
        if re.match(r"\s*(phien|phiên|ngay|ngày|thang|tháng|nam|năm|ma|mã|co phieu|cổ phiếu)", after):
            return True
        if re.search(r"(ngay|ngày|thang|tháng|nam|năm)\s*$", before):
            return True

        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            return True

        if raw.isdigit() and 1900 <= value <= 2100:
            return True
        if raw.isdigit() and value < 10:
            return True
        return False

    fixed = re.sub(
        r"(?<![\w])(?:\d+[.,]\d+|\d+)(?![\w%])",
        lambda match: match.group(0) if should_skip(match) else f"{match.group(0)}%",
        text or "",
    )
    return re.sub(r"(\d+)%([.,])(\d+)%", r"\1\2\3%", fixed)


def clean_chat_output(text: str) -> str:
    fixed = text or ""
    fixed = fixed.replace("**", "")
    fixed = fixed.replace("__", "")
    fixed = re.sub(r"(?m)^\s*#{1,6}\s*", "", fixed)
    fixed = re.sub(
        r"(?<![\w])(\d+[.,]\d+|\d+)%",
        lambda match: f"{float(match.group(1).replace(',', '.')):.1f}%",
        fixed,
    )
    return fixed.strip()



def _find_stock_4key_payload(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        if value.get("ok") and (
            value.get("group_4key")
            or (
                value.get("composite")
                and (
                    "ticker_momentum" in value
                    or "branch_momentum" in value
                    or "smdt_ticker" in value
                    or "smdt_branch" in value
                )
            )
        ):
            return value
        for key in ("result", "data", "results"):
            found = _find_stock_4key_payload(value.get(key))
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_stock_4key_payload(item)
            if found:
                return found
    return None


def latest_stock_4key_payload(messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for message in reversed(messages):
        if message.get("role") != "tool":
            continue
        try:
            payload = json.loads(message.get("content") or "{}")
        except Exception:
            continue
        found = _find_stock_4key_payload(payload)
        if found:
            return found
    return None


def _parse_iso_date(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        return None


def _find_branch_drop_payload(value: Any) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    best_date: Optional[datetime] = None

    def visit(node: Any, branch_name: str = ""):
        nonlocal best, best_date
        if isinstance(node, dict):
            current_branch = str(
                node.get("keyName")
                or node.get("branch")
                or node.get("name")
                or branch_name
            ).strip()
            smdts = node.get("smdts")
            if isinstance(smdts, list):
                for item in smdts:
                    if not isinstance(item, dict):
                        continue
                    parsed_date = _parse_iso_date(item.get("date"))
                    if not parsed_date:
                        continue
                    if best_date is None or parsed_date > best_date:
                        best_date = parsed_date
                        best = {
                            "branch": current_branch,
                            "date": str(item.get("date") or "").strip()[:10],
                            "smdt": item.get("smdt"),
                        }
            for child in node.values():
                visit(child, current_branch)
        elif isinstance(node, list):
            for item in node:
                visit(item, branch_name)

    visit(value)
    return best


def format_branch_drop_answer(payload: Dict[str, Any]) -> str:
    branch = str(payload.get("branch") or "ngành").strip()
    date_text = str(payload.get("date") or "").strip() or "ngày gần nhất"
    smdt = _fmt_metric(payload.get("smdt"), "%")
    return (
        f"Ngành {branch} đã mất vai trò dẫn sóng lần gần nhất vào ngày {date_text} "
        f"khi SMDT của ngành giảm xuống còn {smdt}, dưới ngưỡng 70.0% "
        f"được coi là dấu hiệu mất vai trò dẫn dắt."
    )

def ensure_stock_4key_section(final_text: str, messages: List[Dict[str, Any]]) -> str:
    payload = latest_stock_4key_payload(messages)
    if not payload:
        return final_text or ""

    normalized = normalize_search_text(final_text or "")
    if "nhom 4 key" in normalized:
        return final_text or ""

    group = _display_4key_label(payload.get("group_4key"))
    if not group:
        return final_text or ""
    recommendation = _display_4key_label(payload.get("recommendation"))

    section = f'2. Nhóm 4 Key: Thuộc nhóm "{group}"'
    if recommendation:
        section += f', khuyến nghị "{recommendation}".'
    else:
        section += "."

    text = final_text or ""

    def bump_number(match: re.Match) -> str:
        number = int(match.group(2))
        if number < 2:
            return match.group(0)
        return f"{match.group(1)}{number + 1}{match.group(3)}"

    bumped = re.sub(r"(?m)^(\s*)(\d+)(\.\s+)", bump_number, text)
    insert_at = re.search(r"(?m)^\s*3\.\s+", bumped)
    if insert_at:
        return bumped[:insert_at.start()].rstrip() + "\n\n" + section + "\n\n" + bumped[insert_at.start():].lstrip()
    return bumped.rstrip() + "\n\n" + section



def _derive_4key_group(payload: Dict[str, Any]) -> tuple[str, str]:
    group = str(payload.get("group_4key") or "").strip()
    recommendation = str(payload.get("recommendation") or "").strip()
    if group:
        return group, recommendation

    ticker_momentum = payload.get("ticker_momentum")
    branch_momentum = payload.get("branch_momentum")
    try:
        right_wave = float(ticker_momentum) > 0
        right_branch = float(branch_momentum) > 0
    except (TypeError, ValueError):
        return "Chưa xác định", recommendation or "Chưa đủ dữ liệu xác định nhóm 4 Key"

    if right_wave and right_branch:
        return "\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh", "MUA - t\u00edn hi\u1ec7u thu\u1eadn c\u1ea3 2 chi\u1ec1u"
    if right_wave and not right_branch:
        return "\u0110\u00fang s\u00f3ng - Sai ng\u00e0nh", "C\u00c2N NH\u1eaeC - m\u00e3 m\u1ea1nh ri\u00eang l\u1ebb, ng\u01b0\u1ee3c d\u00f2ng ng\u00e0nh"
    if not right_wave and right_branch:
        return "\u0110\u00fang ng\u00e0nh - Sai s\u00f3ng", "THEO D\u00d5I - ng\u00e0nh thu\u1eadn nh\u01b0ng m\u00e3 ch\u01b0a x\u00e1c nh\u1eadn"
    return "Sai s\u00f3ng - Sai ng\u00e0nh", "TR\u00c1NH - c\u1ea3 2 chi\u1ec1u b\u1ea5t l\u1ee3i"

def _display_lookup_key(value: Any) -> str:
    normalized = normalize_search_text(str(value or "").strip())
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def _display_4key_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    mapping = {
        "dung song dung nganh": "\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh",
        "dung song sai nganh": "\u0110\u00fang s\u00f3ng - Sai ng\u00e0nh",
        "dung nganh sai song": "\u0110\u00fang ng\u00e0nh - Sai s\u00f3ng",
        "sai song dung nganh": "\u0110\u00fang ng\u00e0nh - Sai s\u00f3ng",
        "sai song sai nganh": "Sai s\u00f3ng - Sai ng\u00e0nh",
        "mua manh": "MUA M\u1ea0NH",
        "mua": "MUA",
        "trung lap": "TRUNG L\u1eacP",
        "ban": "B\u00c1N",
        "ban manh": "B\u00c1N M\u1ea0NH",
        "mua tin hieu thuan ca ma va nganh": "MUA - t\u00edn hi\u1ec7u thu\u1eadn c\u1ea3 2 chi\u1ec1u",
        "mua tin hieu thuan ca 2 chieu": "MUA - t\u00edn hi\u1ec7u thu\u1eadn c\u1ea3 2 chi\u1ec1u",
        "can nhac ma manh rieng nguoc dong nganh": "C\u00c2N NH\u1eaeC - m\u00e3 m\u1ea1nh ri\u00eang l\u1ebb, ng\u01b0\u1ee3c d\u00f2ng ng\u00e0nh",
        "can nhac ma manh rieng le nguoc dong nganh": "C\u00c2N NH\u1eaeC - m\u00e3 m\u1ea1nh ri\u00eang l\u1ebb, ng\u01b0\u1ee3c d\u00f2ng ng\u00e0nh",
        "theo doi nganh thuan nhung ma chua xac nhan": "THEO D\u00d5I - ng\u00e0nh thu\u1eadn nh\u01b0ng m\u00e3 ch\u01b0a x\u00e1c nh\u1eadn",
        "tranh ca ma va nganh deu bat loi": "TR\u00c1NH - c\u1ea3 2 chi\u1ec1u b\u1ea5t l\u1ee3i",
        "tranh ca 2 chieu bat loi": "TR\u00c1NH - c\u1ea3 2 chi\u1ec1u b\u1ea5t l\u1ee3i",
        "chua du du lieu xac dinh nhom 4 key": "Ch\u01b0a \u0111\u1ee7 d\u1eef li\u1ec7u x\u00e1c \u0111\u1ecbnh nh\u00f3m 4 Key",
    }
    return mapping.get(_display_lookup_key(text), text)


def _fmt_metric(value: Any, suffix: str = "") -> str:
    if value is None or value == "":
        return "chưa có dữ liệu"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{number:.1f}{suffix}"
    return f"{number:.2f}".rstrip("0").rstrip(".") + suffix


def _fmt_vn_date(value: Any) -> str:
    raw = str(value or "").strip()[:10]
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d")
        return f"{dt.day}/{dt.month}/{dt.year}"
    except ValueError:
        return raw or "hôm nay"


FOUR_KEY_ONLY_PHRASES = (
    "key nao",
    "key gi",
    "co key gi",
    "4 key nao",
    "4key nao",
    "nhom nao",
    "nhom 4 key nao",
    "thuoc key",
    "thuoc nhom",
    "dang thuoc key",
    "dang thuoc nhom",
    "co dung song dung nganh",
    "co dung song sai nganh",
    "co sai song dung nganh",
    "co sai song sai nganh",
    "danh gia",
    "trang thai",
    "phan tich",
)

FOUR_KEY_DETAIL_PHRASES = (
    "score",
    "composite",
    "diem",
    "rating",
    "xep hang",
    "vi sao",
    "tai sao",
    "ly do",
    "giai thich",
    "chi tiet",
    "smdt",
    "suc manh dong tien",
    "dong luc",
    "phan ky",
    "bonus",
    "khuyen nghi",
)

REQUESTED_4KEY_GROUPS = (
    ("dung song dung nganh", ("\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh",)),
    ("dung song sai nganh", ("\u0110\u00fang s\u00f3ng - Sai ng\u00e0nh",)),
    ("sai song dung nganh", ("\u0110\u00fang ng\u00e0nh - Sai s\u00f3ng",)),
    ("dung nganh sai song", ("\u0110\u00fang ng\u00e0nh - Sai s\u00f3ng",)),
    ("sai song sai nganh", ("Sai s\u00f3ng - Sai ng\u00e0nh",)),
)


def is_stock_4key_only_query(user_text: str) -> bool:
    normalized = normalize_search_text(user_text)
    if not normalized:
        return False
    if any(phrase in normalized for phrase in FOUR_KEY_DETAIL_PHRASES):
        return False
    return any(phrase in normalized for phrase in FOUR_KEY_ONLY_PHRASES)


def requested_4key_groups(user_text: str) -> tuple[str, ...]:
    normalized = normalize_search_text(user_text)
    for phrase, groups in REQUESTED_4KEY_GROUPS:
        if phrase in normalized:
            return groups
    return ()


def _change_word(now: Any, prev: Any) -> str:
    try:
        return "tăng" if float(now) >= float(prev) else "giảm"
    except (TypeError, ValueError):
        return "so với"


def format_stock_4key_answer(payload: Dict[str, Any], user_text: str = "") -> str:
    ticker = str(payload.get("ticker") or "mã").strip().upper()
    branch = str(payload.get("branch") or "ngành").strip()
    date_text = _fmt_vn_date(payload.get("date") or payload.get("requested_date"))
    composite = payload.get("composite") or {}
    breakdown = composite.get("breakdown") or {}
    notes = composite.get("notes") or []

    score = _fmt_metric(composite.get("score"))
    rating = _display_4key_label(composite.get("rating"))
    raw_group, raw_recommendation = _derive_4key_group(payload)
    group = _display_4key_label(raw_group)
    recommendation = _display_4key_label(raw_recommendation)

    if is_stock_4key_only_query(user_text):
        requested_groups = requested_4key_groups(user_text)
        if requested_groups:
            if group in requested_groups:
                return f"C\u00f3, {ticker} \u0111ang thu\u1ed9c Nh\u00f3m 4 Key \"{group}\"."
            return f"Kh\u00f4ng, {ticker} \u0111ang thu\u1ed9c Nh\u00f3m 4 Key \"{group}\"."
        return f"{ticker} \u0111ang thu\u1ed9c Nh\u00f3m 4 Key: \"{group}\"."

    lines = [f"Phân tích cổ phiếu {ticker} tính đến ngày {date_text} như sau:", ""]
    lines.append(f"1. Điểm Composite: Cổ phiếu {ticker} có điểm tổng hợp là {score}, xếp hạng \"{rating}\".")
    lines.append("")
    lines.append(f"2. Nhóm 4 Key: \"{group}\", khuyến nghị \"{recommendation}\".")
    lines.append("")
    lines.append("3. SMDT và Động lực:")
    lines.append(
        f" - SMDT của {ticker}: {_fmt_metric(payload.get('smdt_ticker'), '%')}, "
        f"{_change_word(payload.get('smdt_ticker'), payload.get('smdt_ticker_prev'))} từ {_fmt_metric(payload.get('smdt_ticker_prev'), '%')}."
    )
    lines.append(f" - Động lượng của mã: {_fmt_metric(payload.get('ticker_momentum'))}.")
    lines.append(
        f" - SMDT ngành {branch}: {_fmt_metric(payload.get('smdt_branch'), '%')}, "
        f"{_change_word(payload.get('smdt_branch'), payload.get('smdt_branch_prev'))} từ {_fmt_metric(payload.get('smdt_branch_prev'), '%')}; "
        f"động lượng ngành {_fmt_metric(payload.get('branch_momentum'))}."
    )
    lines.append("")

    if composite.get("co_phan_ky"):
        phan_ky = "Có phân kỳ SMDT tăng nhưng giá chưa tăng tương ứng."
    else:
        phan_ky = "Không có phân kỳ."
    lines.append(f"4. Phân kỳ: {phan_ky}")
    lines.append("")

    lines.append("5. Bonus/Ghi chú:")
    lines.append(f" - Bonus phân kỳ: {_fmt_metric(composite.get('bonus_phan_ky', 0))} điểm.")
    if breakdown:
        labels = {
            "smdt_vs_nganh": "SMDT so với ngành",
            "smdt_delta": "Động lượng SMDT",
            "gia_dong_luong": "Động lượng giá",
            "gia_return_1d_pct": "Lợi nhuận 1 ngày (%)",
            "dong_tien": "Dòng tiền",
        }
        parts = [f"{labels.get(key, key)} {_fmt_metric(value)}" for key, value in breakdown.items()]
        lines.append(" - Breakdown: " + "; ".join(parts) + ".")
    for note in notes:
        lines.append(f" - {note}.")

    return "\n".join(lines).strip()

def has_real_ticker(text: str) -> bool:
    return any(match.group(0) not in NON_TICKER_SYMBOLS for match in TICKER_RE.finditer(text or ""))


def is_definition_query(text: str) -> bool:
    normalized = normalize_search_text(text)
    if not normalized:
        return False
    if not any(phrase in normalized for phrase in DEFINITION_INTENT_PHRASES):
        return False
    if has_real_ticker(text):
        return False
    return not any(phrase in normalized for phrase in DATA_INTENT_PHRASES)


def is_stock_related(text: str) -> bool:
    t = (text or "").lower()
    normalized = normalize_search_text(text)
    if any(k in t for k in STOCK_KEYWORDS):
        return True
    if any(k in normalized for k in NORMALIZED_STOCK_KEYWORDS):
        return True
    return bool(TICKER_RE.search(text or ""))


def should_force_rules(user_text: str) -> bool:
    normalized = normalize_search_text(user_text)
    if not normalized or is_definition_query(user_text):
        return False
    if any(phrase in normalized for phrase in FORCE_RULES_PHRASES):
        return True
    if "smdt" in normalized and any(k in normalized for k in SMDT_DATA_INTENT_WORDS):
        return True
    if has_real_ticker(user_text) and any(k in normalized for k in (
        "phan tich", "smdt", "gia", "tin hieu", "dong tien", "mua", "ban",
        "dat chuan", "ma manh", "bat dau manh", "hieu suat", "key nao", "key gi", "co key gi", "thuoc key", "nhom nao", "danh gia", "trang thai", "phan tich", "4 key", "four key", "dung song", "dung nganh", "composite",
    )):
        return True
    return False


def extract_api_from_context(text: str):
    if not text:
        return []
    return list(set(re.findall(r"get[A-Za-z0-9_]+", text)))


def normalize_label(text: str) -> str:
    return (text or "").strip().upper()


def is_waitbuy_explain_query(text: str) -> bool:
    normalized = normalize_search_text(text)
    if is_definition_query(text):
        return False
    if any(k in normalized for k in ("thuyet minh cho mua", "giai thich cho mua", "waitbuy")):
        return True
    if "cho mua" in normalized:
        return any(k in normalized for k in ("hom nay", "ngay", "thang", "nam", "tang", "giam", "cao", "vuot", "phien", "vi du"))
    return False


def extract_requested_signal_period(text: str) -> Dict[str, Any]:
    date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text or "")
    if date_match:
        return {"date": date_match.group(1)}
    year_match = re.search(r"\b(20\d{2})\b", text or "")
    if year_match:
        return {"year": int(year_match.group(1))}
    return {"year": datetime.now().year}


def format_vn_date(value: Any) -> str:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return str(value or "")


def _normalize_waitbuy_lookup_date(text: str) -> Optional[str]:
    value = extract_date_value(text)
    if not value:
        return None

    normalized = normalize_search_text(str(value))
    if normalized == "hom nay":
        return datetime.now().strftime("%Y-%m-%d")

    raw = str(value).strip()
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", raw):
        return raw

    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(20\d{2})", raw)
    if match:
        day, month, year = map(int, match.groups())
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None

    return None


def is_waitbuy_value_query(text: str) -> bool:
    normalized = normalize_search_text(text)
    if is_definition_query(text):
        return False
    if not ("cho mua" in normalized or "waitbuy" in normalized):
        return False
    if any(k in normalized for k in ("thuyet minh", "giai thich", "vi sao", "tai sao")):
        return False
    return _normalize_waitbuy_lookup_date(text) is not None


def extract_stock_wave_rows(raw: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    def visit(node: Any):
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict):
            return
        if "date" in node and any(key in node for key in ("waitbuy", "buy", "sell", "waitsell")):
            rows.append(node)
            return
        for key in ("waveDatas", "stockWaveDatas", "data", "items", "records", "result", "results"):
            if key in node:
                visit(node.get(key))

    visit(raw)
    return rows


def format_waitbuy_value_answer(row: Dict[str, Any], requested_date: str) -> str:
    date_text = format_vn_date(row.get("date") or requested_date)
    waitbuy = row.get("waitbuy")
    if waitbuy in (None, ""):
        return f"Phiên {date_text} chưa có dữ liệu chờ mua."
    return f"Phiên {date_text} có {waitbuy} cổ phiếu chờ mua."


def extract_recent_total_trade_request(text: str) -> Optional[Dict[str, Any]]:
    normalized = normalize_search_text(text)
    match = re.search(r"\b(\d{1,3})\s+phien\s+gan\s+nhat\b", normalized)
    if not match:
        return None

    if not any(
        phrase in normalized
        for phrase in ("chi so", "gia", "lich su", "ohlc", "open", "high", "low", "close", "vnindex")
    ):
        return None

    ticker = None
    for token in re.findall(r"\b[A-Z][A-Z0-9]{1,6}\b", text or ""):
        token = token.upper()
        if token in ALLOWED_TICKERS or token in MARKET_INDEX_TICKERS:
            ticker = token
            break

    if not ticker:
        return None

    last_dates = int(match.group(1))
    if last_dates <= 0:
        return None

    return {"ticker": ticker, "lastDates": min(last_dates, 120)}


def is_recent_total_trade_query(text: str) -> bool:
    return extract_recent_total_trade_request(text) is not None


def _format_trade_number(value: Any) -> str:
    if value in (None, ""):
        return "NA"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.2f}".rstrip("0").rstrip(".")


def format_recent_total_trade_answer(ticker: str, rows: List[Dict[str, Any]], last_dates: int) -> str:
    if not rows:
        return f"Chưa có dữ liệu {ticker} trong {last_dates} phiên gần nhất."

    lines = [f"{ticker} trong {last_dates} phiên gần nhất:"]
    for row in rows:
        date_text = format_vn_date(row.get("date"))
        open_value = _format_trade_number(row.get("open"))
        high_value = _format_trade_number(row.get("high"))
        low_value = _format_trade_number(row.get("low"))
        close_value = _format_trade_number(row.get("close"))
        lines.append(
            f"- {date_text}: close {close_value}, open {open_value}, high {high_value}, low {low_value}"
        )
    return "\n".join(lines)


def extract_recent_stock_wave_request(text: str) -> Optional[Dict[str, Any]]:
    normalized = normalize_search_text(text)
    match = re.search(r"\b(\d{1,3})\s+phien\s+gan\s+nhat\b", normalized)
    if not match:
        return None

    if "chan song" in normalized:
        return None

    is_wave_metric = any(
        phrase in normalized
        for phrase in (
            "do song",
            "so lieu do song",
            "so lieu song",
            "stock wave",
            "cho mua",
            "cho ban",
            "tin hieu mua",
            "tin hieu ban",
            "do tin cay",
            "waitbuy",
            "waitsell",
        )
    )
    if not is_wave_metric:
        return None

    last_dates = int(match.group(1))
    if last_dates <= 0:
        return None

    year_match = re.search(r"\b(20\d{2})\b", normalized)
    year = int(year_match.group(1)) if year_match else datetime.now().year
    return {"date": str(year), "lastDates": min(last_dates, 120)}


def is_recent_stock_wave_query(text: str) -> bool:
    return extract_recent_stock_wave_request(text) is not None


def recent_stock_wave_rows(raw: Any, last_dates: int) -> List[Dict[str, Any]]:
    rows = extract_stock_wave_rows(raw)
    rows = [row for row in rows if _parse_iso_date(row.get("date"))]
    rows.sort(key=lambda row: _parse_iso_date(row.get("date")) or datetime.min, reverse=True)
    return rows[:last_dates]


def format_recent_stock_wave_answer(rows: List[Dict[str, Any]], last_dates: int) -> str:
    if not rows:
        return f"Chưa có dữ liệu dò sóng trong {last_dates} phiên gần nhất."

    lines = [f"Số liệu dò sóng {last_dates} phiên gần nhất:"]
    for row in rows:
        date_text = format_vn_date(row.get("date"))
        parts = [
            f"mua {_format_trade_number(row.get('buy'))}",
            f"bán {_format_trade_number(row.get('sell'))}",
            f"chờ mua {_format_trade_number(row.get('waitbuy'))}",
            f"chờ bán {_format_trade_number(row.get('waitsell'))}",
            f"tổng {_format_trade_number(row.get('total'))}",
        ]
        reliability = row.get("reliability")
        if reliability not in (None, ""):
            parts.append(f"độ tin cậy {_format_trade_number(reliability)}%")
        lines.append(f"- {date_text}: " + ", ".join(parts))
    return "\n".join(lines)

# ORCHESTRATOR
class Orchestrator:

    def __init__(self, memory: MemoryStore, rag: RAGStore, registry: ToolRegistry):

        self.memory = memory
        self.rag = rag
        self.registry = registry

        self.executor = APIExecutor(registry)
        self.oa = OpenAIClient()
        self.question_guide = QuestionGuide(
            self.rag,
            memory=self.memory,
            openai_client=self.oa,
        )
        self._user_chat_locks: Dict[str, asyncio.Lock] = {}

    # =====================================================
    # BUILD BASE MESSAGES
    # =====================================================

    def classify_query_source(self, user_text: str) -> str:
        if should_force_rules(user_text):
            return "RULES"

        prompt = f"""
    Bạn là bộ phân loại rất ngắn cho chatbot chứng khoán.

    Nhiệm vụ:
    - Trả về đúng 1 nhãn duy nhất: RULES hoặc BOOKS

    RULES:
    - Lộ trình, thống kê
    - câu hỏi dữ liệu
    - câu hỏi cần API
    - hỏi giá, SMDT, tín hiệu, chờ mua, chờ bán, mã nào, ngành nào, ngày nào, thống kê
    - hỏi “dòng/ngành nào dẫn sóng từ khi nào”, “bắt đầu dẫn sóng khi nào”, “dẫn sóng từ ngày/tháng nào”, "thời điểm đạt chuẩn ngành mạnh của một ngành/dòng/mã"


    BOOKS:
    - câu hỏi kiến thức
    - câu hỏi giải thích, khái niệm, vì sao, bản chất, học thuyết, tiêu chí, nên hiểu thế nào

    Câu hỏi:
    {user_text}

    Chỉ trả về RULES hoặc BOOKS.
    """.strip()

        resp = self.oa.chat(
            model=CLASSIFIER_MODEL,
            messages=[
                {"role": "system", "content": "Chỉ trả về đúng 1 từ: RULES hoặc BOOKS."},
                {"role": "user", "content": prompt},
            ]
        )

        raw = normalize_label(resp.choices[0].message.content or "")

        if raw not in {"RULES", "BOOKS"}:
            return "RULES"

        return raw

    async def build_base_messages(
        self,
        user_id: str,
        user_text: str,
        language: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool, List[str], Optional[str]]:

        raw_user_text = user_text.strip()
        query_source = self.classify_query_source(raw_user_text)
        allowed_apis: List[str] = []
        current_doc: Optional[str] = None

        print("QUERY SOURCE:", query_source)
        history_all = await self.memory.recent_messages(user_id)

        def is_semantically_related(current: str, previous: str) -> bool:
            if not previous:
                return False

            cur_words = set(current.lower().split())
            prev_words = set(previous.lower().split())

            stop = {"là","bao","nhiêu","có","không","k","gì","sao","thì","vậy"}
            cur_words -= stop
            prev_words -= stop

            overlap = cur_words.intersection(prev_words)

            return len(overlap) >= 2


        history = []

        if history_all:
            recent_candidates = history_all[-3:]

            for h in reversed(recent_candidates):
                if is_semantically_related(raw_user_text, h["content"]):
                    history = history_all[-3:] 
                    break

        # ======================================
        # STOCK RELATED DETECTION
        # ======================================

        stock_related = is_stock_related(raw_user_text)

        if not stock_related:
            for h in reversed(history):
                if is_stock_related(h["content"]):
                    stock_related = True
                    break

        today_str = datetime.now().strftime("%Y-%m-%d")

        # ======================================
        # BUILD SYSTEM MESSAGE (ONLY 1)
        # ======================================

        system_parts = [
            SYSTEM_PROMPT,
            "Output format rule: trả lời dạng text thường, không dùng markdown, không dùng dấu ** hoặc __ để in đậm.",
            "SMDT formatting rule: SMDT is a percentage metric. Whenever you mention a numeric SMDT value, always append the % symbol, for example 15.57% or 70%.",
            "QUY TẮC WHITELIST MÃ CỔ PHIẾU BẮT BUỘC:\n"
            "- Chỉ được sử dụng hoặc nhắc tới các mã sau: " + allowed_tickers_text() + ".\n"
            "- Không được tự bổ sung, suy đoán, ví dụ hoặc nhắc tới bất kỳ mã cổ phiếu nào ngoài danh sách.\n"
            "- Nếu dữ liệu chứa mã ngoài danh sách thì phải bỏ qua hoàn toàn mã đó.",
        ]

        if stock_related:
            branches_text = "\n".join([f"- {b}" for b in MAIN_BRANCHES])
            aliases_text = "\n".join([f"- {alias} = {canonical}" for alias, canonical in MAIN_BRANCH_ALIASES.items()])
            system_parts.append(
                "DANH SÁCH 6 NGÀNH CHỦ LỰC CỦA STOCKTRADERS AI - PHẢI GHI NHỚ TUYỆT ĐỐI:\n"
                + branches_text
                + "\n\n"
                + "QUY TẮC BẮT BUỘC VỀ NGÀNH CHỦ LỰC:\n"
                + "- 6 ngành trên luôn là ngành chủ lực trong hệ thống StockTraders AI.\n"
                + "- Tuyệt đối không gọi bất kỳ ngành nào trong danh sách này là ngành phụ.\n"
                + "- Nếu tài liệu hoặc ngữ cảnh có chữ 'ngành phụ' mâu thuẫn với danh sách này, phải ưu tiên danh sách 6 ngành chủ lực.\n"
                + "- Bất động sản dân cư là ngành chủ lực, không phải ngành phụ.\n"
                + "- BĐS dân cư/BDS dân cư là cách gọi tắt của Bất động sản dân cư.\n"
                + "\n"
                + "ALIAS NGÀNH CHỦ LỰC:\n"
                + aliases_text
                + "\n\nQUY TAC SACH VE NGANH CHU LUC:\n6 nganh chu luc cua StockTraders AI la:\n"
                + branches_text
                + "\n- Neu user hoi tong quat ve 'nganh chu luc', 'suc manh dong tien nganh chu luc', "
                + "hoac SMDT cua cac nganh chu luc, phai kiem tra/de cap du 6 nganh tren.\n"
                + "- Khong duoc tu bo sot Chung khoan. Neu khong co du lieu cho mot nganh, noi ro nganh do chua co du lieu.\n"
                + "- Neu user hoi rieng 'Chung khoan' hoac 'nganh chung khoan', can dung nganh Chung khoan/Moi gioi chung khoan."
            )

        if language == "en":
            system_parts.append(f"Today is {today_str}")
        else:
            system_parts.append(f"Ngày hiện tại là {today_str}")

        sources = []

        # ======================================
        # RAG CONTEXT
        # ======================================

        if query_source == "BOOKS":
            book_result = self.rag.retrieve_best_book(raw_user_text, top_k=3)
            doc = book_result.get("doc_name")
            score = book_result.get("score")
            chunks = book_result.get("chunks") or []

            print(f"\nBOOK DOC: {doc} | SCORE: {score}")

            for i, ch in enumerate(chunks, 1):
                preview = ch.replace("\n", " ")[:120]
                print(f"CHUNK {i}: {preview}...")

            current_doc = book_result.get("doc_name")
            book_chunks = book_result.get("chunks") or []

            if book_chunks:
                refs = []
                for i, ch in enumerate(book_chunks, start=1):
                    refs.append(f"[{i}] {ch}")

                system_parts.append("""BOOK KNOWLEDGE CONTEXT - STOCKTRADERS AI.
                    RULES:
                    - Chỉ trả lời dựa trên nội dung trong tài liệu bên dưới.
                    - Nếu user hỏi dạng "là gì", "khái niệm", "nghĩa là gì", "hiểu thế nào", hãy diễn giải thành 3-5 câu ngắn, rõ ý.
                    - Được tóm tắt và viết lại cho dễ hiểu, không bắt buộc giữ nguyên câu chữ trong tài liệu.
                    - Giải thích theo kiểu người mới cũng hiểu: nó là gì, dấu hiệu nào cần chú ý, và nên hiểu đúng ra sao.
                    - Không copy nguyên một đoạn dài, không bịa thêm ngoài tài liệu, không nhắc tài liệu nội bộ.
                    KNOWLEDGE:
                    """ + "\n\n".join(refs)
                    )

        elif stock_related:
            doc = await self.rag.pick_doc(raw_user_text)
            current_doc = doc

            chunks = self.rag.load_chunks(doc)
            ctx = self.rag.build_context(doc, chunks, raw_user_text)

            rules = (ctx.get("rules") or "").strip()
            refs = (ctx.get("refs") or "").strip()
            allowed_apis = extract_api_from_context(refs)

            if rules:
                system_parts.append(
                    "QUY TRÌNH XỬ LÝ BẮT BUỘC:\n" + rules
                )

            if refs:
                system_parts.append(
                    "KHUNG PHÂN TÍCH NỘI BỘ STOCKTRADERS AI:\n" + refs
                )

        system_text = "\n\n".join(system_parts)

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": system_text
            }
        ]

        # ======================================
        # HISTORY (SMART INJECTION)
        # ======================================

        for h in history:
            if h["role"] in ("user", "assistant"):
                messages.append({
                    "role": h["role"],
                    "content": sanitize_response_text(h["content"])
                })

        # Current user message
        messages.append({
            "role": "user",
            "content": raw_user_text
        })

        enable_tools = (query_source == "RULES" and stock_related)
        return messages, sources, enable_tools, allowed_apis, current_doc

    # =====================================================
    # TOOL LOOP
    # =====================================================

    def _run_tool_loop(
            self,
            model: str,
            messages: List[Dict[str, Any]],
            enable_tools: bool,
            allowed_apis: Optional[List[str]] = None,
            current_doc: Optional[str] = None,
            user_text: str = "",
        ) -> Tuple[List[Dict[str, Any]], str]:

        if not enable_tools:

            resp = self.oa.chat(
                model=model,
                messages=messages
            )

            final_text = resp.choices[0].message.content or ""

            messages.append({
                "role": "assistant",
                "content": final_text
            })

            return messages, final_text

        tools = self.registry.tools

        if allowed_apis:

            tools = [
                t for t in tools
                if t["function"]["name"] in allowed_apis
            ]
        loops = 0

        while loops < MAX_TOOL_LOOPS:

            loops += 1

            log("\n================ TOOL LOOP =================")
            log("LOOP:", loops)

            resp = self.oa.chat(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )

            msg = resp.choices[0].message

            assistant_msg = {
                "role": "assistant",
                "content": msg.content or ""
            }

            # Nếu GPT gọi tool
            if getattr(msg, "tool_calls", None):

                assistant_msg["tool_calls"] = []

                for tc in msg.tool_calls:

                    assistant_msg["tool_calls"].append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })

            messages.append(assistant_msg)

            # Nếu không có tool call → kết thúc
            if not getattr(msg, "tool_calls", None):

                final_text = ensure_stock_4key_section(msg.content or "", messages)
                return messages, final_text

            # Chạy tool
            for tc in msg.tool_calls:

                op_name = tc.function.name

                log("🔧 TOOL CALL:", op_name)
                log("ARGS:", tc.function.arguments)

                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}

                result = self.executor.call(op_name, args, doc_name=current_doc, user_text=user_text)

                log("API RESULT TYPE:", type(result))

                if isinstance(result, list):
                    log("API RESULT SIZE:", len(result))

                if op_name == "getAnalyzeWave":
                    if isinstance(result, dict) and "message" in result:
                        return messages, result["message"]
    
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False)
                })

                if op_name == "getSMDTBranchDrop":
                    branch_drop_payload = _find_branch_drop_payload(result)
                    if branch_drop_payload:
                        final_text = format_branch_drop_answer(branch_drop_payload)
                        log("BRANCH DROP FORMATTER APPLIED")
                        return messages, final_text

                if op_name == "getStock4KeyEvaluation":
                    stock_4key_payload = _find_stock_4key_payload(result)
                    if stock_4key_payload:
                        final_text = format_stock_4key_answer(stock_4key_payload, user_text=user_text)
                        log("4KEY FORMATTER APPLIED")
                        return messages, final_text

        final_text = "Tool loop vượt quá giới hạn."

        return messages, final_text

    # =====================================================
    # STREAM
    # =====================================================

    async def _find_waitbuy_target(self):
        targets = await self.memory.list_sales_discovery_targets(
            active_only=True,
            confirmed_only=True,
        )
        for target in targets:
            haystack = " ".join([
                str(target.get("target_key") or ""),
                str(target.get("name") or ""),
                str(target.get("description") or ""),
                str(target.get("suggested_question") or ""),
            ])
            normalized = normalize_search_text(haystack)
            if "cho mua" in normalized and any(
                keyword in normalized
                for keyword in ("thuyet minh", "giai thich", "waitbuy")
            ):
                return target
        return None

    def _answer_recent_stock_wave(self, user_text: str) -> str:
        request = extract_recent_stock_wave_request(user_text)
        if not request:
            return "Anh/chị muốn xem số liệu dò sóng bao nhiêu phiên gần nhất?"

        api_args = {"date": request["date"]}
        raw_wave = self.executor.call(
            "getStockWave",
            api_args,
            user_text=user_text,
        )
        rows = recent_stock_wave_rows(raw_wave, request["lastDates"])
        return format_recent_stock_wave_answer(rows, request["lastDates"])

    def _answer_recent_total_trade(self, user_text: str) -> str:
        request = extract_recent_total_trade_request(user_text)
        if not request:
            return "Anh/chị muốn xem chỉ số/mã nào và bao nhiêu phiên gần nhất?"

        raw_trade = self.executor.call(
            "getTotalTrade",
            request,
            user_text=user_text,
        )
        rows = extract_rows(raw_trade, ("totalTradeDatas", "tradeDatas", "records", "items"))
        return format_recent_total_trade_answer(
            request["ticker"],
            rows,
            request["lastDates"],
        )

    def _answer_waitbuy_value(self, user_text: str) -> str:
        requested_date = _normalize_waitbuy_lookup_date(user_text)
        if not requested_date:
            return "Anh/chị muốn xem chờ mua ngày nào?"

        raw_wave = self.executor.call(
            "getStockWave",
            {"date": requested_date},
            user_text=user_text,
        )
        rows = extract_stock_wave_rows(raw_wave)
        row = next(
            (
                item for item in rows
                if str(item.get("date") or "").strip()[:10] == requested_date
            ),
            rows[0] if rows else None,
        )

        if not row:
            return f"Phiên {format_vn_date(requested_date)} chưa có dữ liệu chờ mua."

        return format_waitbuy_value_answer(row, requested_date)

    async def _answer_waitbuy_explanation(self, user_text: str, model: str) -> str:
        target = await self._find_waitbuy_target()
        period = extract_requested_signal_period(user_text)
        year = str(period.get("date") or period.get("year") or datetime.now().year)[:4]

        raw_total_trade = self.executor.call(
            "getTotalTrade",
            {"ticker": "VNINDEX", "date": year},
        )
        raw_wave = self.executor.call("getStockWave", {"date": year})
        scan = scan_vnindex_waitbuy_reversal(
            extract_rows(raw_total_trade, ("totalTradeDatas", "tradeDatas", "records", "items")),
            extract_rows(raw_wave, ("waveDatas", "stockWaveDatas", "items")),
        )
        latest = scan.get("latest")

        if not latest:
            return f"Năm {year} chưa có phiên nào thỏa điều kiện chờ mua tăng mạnh sau phiên VNINDEX giảm."

        fallback = (
            f"Phiên {format_vn_date(latest['date'])} đáng chú ý: VNINDEX giảm "
            f"{abs(latest['close_change']):g} điểm so với phiên trước, trong khi chờ mua tăng từ "
            f"{latest['prev_waitbuy']:g} lên {latest['waitbuy']:g} mã "
            f"(+{latest['waitbuy_change']:g})."
        )
        target_prompt = (
            (target or {}).get("suggested_question")
            or (target or {}).get("description")
            or "Sau các phiên giảm mạnh thì chờ mua dễ tăng cao, như các phiên lấy ví dụ ra"
        )
        required_data = {
            "date": format_vn_date(latest.get("date")),
            "prev_date": format_vn_date(latest.get("prev_date")),
            "vnindex_down_points": abs(latest.get("close_change") or 0),
            "prev_waitbuy": latest.get("prev_waitbuy"),
            "waitbuy": latest.get("waitbuy"),
            "waitbuy_change": latest.get("waitbuy_change"),
        }
        prompt = f"""
Bạn là chatbot StockTraders AI đang nói chuyện với khách.

Prompt gợi ý của admin:
{target_prompt}

Số liệu bắt buộc dùng:
{json.dumps(required_data, ensure_ascii=False, indent=2)}

Yêu cầu:
- Viết 1 câu tự nhiên, ngắn gọn cho khách.
- Phải bám theo prompt gợi ý của admin để diễn giải ý nghĩa.
- Chỉ dùng số liệu bắt buộc ở trên, không bịa thêm.
- Không nhắc API, không nói "dữ liệu lấy từ", không giải thích định nghĩa nguyên lý.
- Không khuyến nghị mua/bán, không khẳng định thị trường chắc chắn tăng.
- Nếu cần diễn giải, chỉ nói nhẹ kiểu lực quan tâm/chờ mua quay lại sau phiên giảm.
""".strip()

        try:
            resp = self.oa.chat(
                model=model,
                messages=[
                    {"role": "system", "content": "Chỉ trả lời tiếng Việt, 1 câu ngắn, tự nhiên, không markdown."},
                    {"role": "user", "content": prompt},
                ],
                tools=None,
                tool_choice="auto",
            )
            text = (resp.choices[0].message.content or "").strip()
            return text or fallback
        except Exception as exc:
            print("WAITBUY_EXPLANATION_ERROR:", exc)
            return fallback
    async def chat_stream(
        self,
        user_id: str,
        user_text: str,
        language: str,
        selected_model: Optional[str],
        skip_question_guide: bool = False
    ):

        lock = self._user_chat_locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            async for event, data in self._chat_stream_unlocked(
                user_id=user_id,
                user_text=user_text,
                language=language,
                selected_model=selected_model,
                skip_question_guide=skip_question_guide,
            ):

                yield event, data

    async def _chat_stream_unlocked(
        self,
        user_id: str,
        user_text: str,
        language: str,
        selected_model: Optional[str],
        skip_question_guide: bool = False
    ):

        model = pick_model(selected_model)
        reset_token_usage()

        def done_data(sources):
            return {"sources": sources, "usage": current_token_usage()}

        await self.memory.add(user_id, "user", user_text)

        if find_disallowed_tickers(user_text):
            final_text = "Mã được hỏi không nằm trong danh sách mã được hệ thống hỗ trợ."
            for i in range(0, len(final_text), STREAM_CHUNK_CHARS):
                chunk = final_text[i:i + STREAM_CHUNK_CHARS]
                if chunk:
                    yield ("delta", {"text": chunk})
            await self.memory.add(user_id, "assistant", final_text)
            yield ("done", done_data([]))
            return

        guide_result = None if skip_question_guide else await self.question_guide.handle(user_id, user_text)
        if guide_result and guide_result.action == "ask":

            final_text = clean_chat_output(sanitize_response_text(guide_result.message))
            full = ""
            for i in range(0, len(final_text), STREAM_CHUNK_CHARS):
                chunk = final_text[i:i + STREAM_CHUNK_CHARS]
                if chunk:
                    full += chunk
                    yield ("delta", {"text": chunk})
            await self.memory.add(user_id, "assistant", full)
            yield ("done", done_data([]))
            return

        guided_question = False
        if guide_result and guide_result.action == "run" and guide_result.canonical_question:
            user_text = guide_result.canonical_question
            guided_question = True

        if is_recent_stock_wave_query(user_text):
            final_text = self._answer_recent_stock_wave(user_text)
            final_text = clean_chat_output(sanitize_response_text(final_text))
            full = ""
            for i in range(0, len(final_text), STREAM_CHUNK_CHARS):
                chunk = final_text[i:i + STREAM_CHUNK_CHARS]
                if chunk:
                    full += chunk
                    yield ("delta", {"text": chunk})
            await self.memory.add(user_id, "assistant", full)
            yield ("done", done_data([]))
            return

        if is_recent_total_trade_query(user_text):
            final_text = self._answer_recent_total_trade(user_text)
            final_text = clean_chat_output(sanitize_response_text(final_text))
            full = ""
            for i in range(0, len(final_text), STREAM_CHUNK_CHARS):
                chunk = final_text[i:i + STREAM_CHUNK_CHARS]
                if chunk:
                    full += chunk
                    yield ("delta", {"text": chunk})
            await self.memory.add(user_id, "assistant", full)
            yield ("done", done_data([]))
            return

        if is_waitbuy_value_query(user_text):
            final_text = self._answer_waitbuy_value(user_text)
            final_text = clean_chat_output(sanitize_response_text(final_text))
            full = ""
            for i in range(0, len(final_text), STREAM_CHUNK_CHARS):
                chunk = final_text[i:i + STREAM_CHUNK_CHARS]
                if chunk:
                    full += chunk
                    yield ("delta", {"text": chunk})
            await self.memory.add(user_id, "assistant", full)
            yield ("done", done_data([]))
            return

        if not guided_question and is_waitbuy_explain_query(user_text):
            final_text = await self._answer_waitbuy_explanation(user_text=user_text, model=model)
            final_text = clean_chat_output(sanitize_response_text(final_text))
            full = ""
            for i in range(0, len(final_text), STREAM_CHUNK_CHARS):
                chunk = final_text[i:i + STREAM_CHUNK_CHARS]
                if chunk:
                    full += chunk
                    yield ("delta", {"text": chunk})
            await self.memory.add(user_id, "assistant", full)
            yield ("done", done_data([]))
            return

        base_messages, sources, enable_tools, allowed_apis, current_doc = await self.build_base_messages(
            user_id,
            user_text,
            language,
        )
        loop_messages, final_text = self._run_tool_loop(
            model,
            base_messages,
            enable_tools=enable_tools,
            allowed_apis=allowed_apis,
            current_doc=current_doc,
            user_text=user_text,
        )
        final_text = ensure_stock_4key_section(final_text, loop_messages)
        final_text = enforce_main_branch_terms(final_text)
        final_text = ensure_smdt_percent(final_text)
        final_text = clean_chat_output(sanitize_response_text(final_text))

        full = ""
        for i in range(0, len(final_text), STREAM_CHUNK_CHARS):
            chunk = final_text[i:i + STREAM_CHUNK_CHARS]
            if chunk:
                full += chunk
                yield ("delta", {"text": chunk})

        await self.memory.add(user_id, "assistant", full)
        yield ("done", done_data(sources))

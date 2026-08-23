import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.constants import MAIN_BRANCHES, MAIN_BRANCH_ALIASES
from services.ticker_policy import ALLOWED_TICKERS

STATE_TTL_MINUTES = 120
NON_TICKER_SYMBOLS = {"RSI", "NAV", "SMDT", "GPT", "AI", "API", "MACD"}
MARKET_WAVE_METRICS = {
    "waitbuy": {
        "label": "chờ mua",
        "aliases": ("cho mua", "waitbuy", "wait buy"),
    },
    "waitsell": {
        "label": "chờ bán",
        "aliases": ("cho ban", "waitsell", "wait sell"),
    },
    "buy": {
        "label": "mua",
        "aliases": ("tin hieu mua", "mua"),
    },
    "sell": {
        "label": "bán",
        "aliases": ("tin hieu ban", "ban"),
    },
    "reliability": {
        "label": "độ tin cậy",
        "aliases": ("do tin cay", "reliability"),
    },
    "total": {
        "label": "tổng",
        "aliases": ("tong", "tong so"),
    },
}
MARKET_WAVE_LOOKUP_CUES = (
    "bao nhieu",
    "ngay",
    "phien",
    "hom nay",
    "hien nay",
    "hien tai",
    "so lieu",
    "moc",
    "dat moc",
)
MARKET_WAVE_EXPLAIN_CUES = ("la gi", "nghia la gi", "giai thich", "thuyet minh", "vi sao", "tai sao")
FOUR_KEY_GROUP_PHRASES = (
    ("dung song dung nganh", "dd"),
    ("dung song sai nganh", "ds"),
    ("sai song dung nganh", "sd"),
    ("dung nganh sai song", "sd"),
    ("sai song sai nganh", "ss"),
)
FOUR_KEY_GROUP_LABELS = {
    "dd": "đúng sóng đúng ngành",
    "ds": "đúng sóng sai ngành",
    "sd": "sai sóng đúng ngành",
    "ss": "sai sóng sai ngành",
}
FOUR_KEY_SCREEN_LIST_CUES = (
    "cung cap",
    "danh sach",
    "danh muc",
    "cac ma",
    "nhung ma",
    "liet ke",
    "loc",
)
STOCK_4KEY_DETAIL_CUES = (
    "vi sao",
    "tai sao",
    "ly do",
    "giai thich",
    "chi tiet",
    "smdt",
    "composite",
    "score",
    "diem",
    "phan ky",
    "bonus",
    "dong luc",
    "khuyen nghi",
)


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = normalized.replace("đ", "d").replace("Đ", "D")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9/\-\s]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def display_date(value: Optional[str]) -> str:
    if not value:
        return ""
    if value == "today":
        return "hôm nay"
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(value)


def normalize_date(text: str, now: datetime) -> Optional[str]:
    normalized = normalize_text(text)
    if any(phrase in normalized for phrase in ("hom nay", "hien nay", "hien tai", "bay gio")):
        return now.strftime("%Y-%m-%d")
    if "hom kia" in normalized:
        return (now - timedelta(days=2)).strftime("%Y-%m-%d")
    if "hom qua" in normalized:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")

    match = re.search(r"\b(20\d{2})[-/](\d{1,2})(?:[-/](\d{1,2}))?\b", normalized)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3) or 1)
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None

    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", normalized)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        raw_year = match.group(3)
        year = now.year if not raw_year else int(raw_year)
        if year < 100:
            year += 2000
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None

    return None


def apply_time_relation(base_date: Optional[str], relation: Optional[str]) -> Optional[str]:
    if not base_date or not relation:
        return base_date
    try:
        date_value = datetime.strptime(base_date, "%Y-%m-%d")
    except ValueError:
        return base_date
    if relation == "next_day":
        return (date_value + timedelta(days=1)).strftime("%Y-%m-%d")
    if relation == "prev_day":
        return (date_value - timedelta(days=1)).strftime("%Y-%m-%d")
    return base_date


def extract_tickers(text: str) -> List[str]:
    tickers: List[str] = []
    for raw in re.findall(r"\b[A-Z][A-Z0-9]{1,6}\b", text or ""):
        ticker = raw.upper()
        if ticker in ALLOWED_TICKERS and ticker not in NON_TICKER_SYMBOLS and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def text_has_phrase(normalized: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", normalized) is not None


def extract_market_wave_metric(normalized: str, has_tickers: bool = False) -> Optional[str]:
    aliases: List[tuple[str, str]] = []
    for metric, config in MARKET_WAVE_METRICS.items():
        for alias in config["aliases"]:
            aliases.append((alias, metric))

    for alias, metric in sorted(aliases, key=lambda item: len(item[0]), reverse=True):
        if metric in {"buy", "sell"} and has_tickers and alias in {"mua", "ban"}:
            continue
        if text_has_phrase(normalized, alias):
            return metric
    return None


def is_market_wave_lookup(normalized: str, parsed: Dict[str, Any], metric: Optional[str]) -> bool:
    if not metric:
        return False
    if any(text_has_phrase(normalized, cue) for cue in MARKET_WAVE_EXPLAIN_CUES):
        return False
    return bool(
        parsed.get("time_context")
        or parsed.get("time_relation")
        or any(text_has_phrase(normalized, cue) for cue in MARKET_WAVE_LOOKUP_CUES)
    )


def extract_branch_entity(text: str) -> Optional[str]:
    normalized = normalize_text(text)
    candidates = list(MAIN_BRANCHES) + list(MAIN_BRANCH_ALIASES.keys())
    for candidate in candidates:
        if normalize_text(candidate) in normalized:
            return MAIN_BRANCH_ALIASES.get(candidate, candidate)

    match = re.search(r"\b(?:nganh|dong tien nganh|dong)\s+([a-z0-9\s]+)", normalized)
    if not match:
        return None
    value = re.split(
        r"\b(?:hom nay|hien nay|ngay|phien|the nao|bao nhieu|co nen|khong|ko)\b",
        match.group(1),
        maxsplit=1,
    )[0].strip()
    return value or None


def extract_4key_screen_group(normalized: str) -> Optional[str]:
    for phrase, code in FOUR_KEY_GROUP_PHRASES:
        if phrase in normalized:
            return code
    return None


def is_4key_screen_list_query(normalized: str) -> bool:
    return any(text_has_phrase(normalized, cue) for cue in FOUR_KEY_SCREEN_LIST_CUES)


def parse_query(text: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now()
    raw = text or ""
    normalized = normalize_text(raw)
    tickers = extract_tickers(raw)
    branch = extract_branch_entity(raw)
    entities = tickers[:]
    if branch and not entities:
        entities.append(branch)

    parsed: Dict[str, Any] = {
        "raw_query": raw,
        "intent": None,
        "topic": None,
        "metric": None,
        "entities": entities,
        "time_context": normalize_date(raw, now),
        "time_relation": None,
        "comparison_entity": None,
        "missing_fields": [],
        "is_followup_like": False,
    }

    if any(phrase in normalized for phrase in ("ngay hom sau", "hom sau", "phien sau", "ngay sau")):
        parsed["time_relation"] = "next_day"
    elif any(phrase in normalized for phrase in ("ngay hom truoc", "hom truoc", "phien truoc", "ngay truoc")):
        parsed["time_relation"] = "prev_day"

    market_wave_metric = extract_market_wave_metric(normalized, has_tickers=bool(tickers))
    if is_market_wave_lookup(normalized, parsed, market_wave_metric):
        parsed["intent"] = "metric_lookup"
        parsed["topic"] = "market_wave"
        parsed["metric"] = market_wave_metric
    elif "smdt" in normalized or "suc manh dong tien" in normalized:
        parsed["intent"] = "metric_lookup"
        parsed["topic"] = "stock_metric" if tickers else "branch_metric"
        parsed["metric"] = "SMDT"
    elif "dong tien" in normalized:
        parsed["intent"] = "analysis"
        parsed["topic"] = "cashflow"
    elif extract_4key_screen_group(normalized) and is_4key_screen_list_query(normalized):
        parsed["intent"] = "analysis"
        parsed["topic"] = "stock_4key_screen"
        parsed["metric"] = extract_4key_screen_group(normalized)
    elif any(phrase in normalized for phrase in ("4 key", "four key", "key nao", "key gi", "thuoc key", "dung song", "sai song")):
        parsed["intent"] = "analysis"
        parsed["topic"] = "stock_4key"
    elif any(phrase in normalized for phrase in ("gia", "bao nhieu")) and tickers:
        parsed["intent"] = "metric_lookup"
        parsed["topic"] = "price"
        parsed["metric"] = "price"
    elif tickers and any(phrase in normalized for phrase in ("phan tich", "the nao", "co nen", "mua", "ban")):
        parsed["intent"] = "analysis"
        parsed["topic"] = "stock_analysis"

    comparative = normalized.startswith("so voi") or " so voi " in f" {normalized} "
    if comparative and tickers:
        parsed["comparison_entity"] = tickers[-1]

    token_count = len(normalized.split())
    only_entity = bool(tickers) and token_count <= 3
    only_date = bool(parsed["time_context"] or parsed["time_relation"]) and token_count <= 5
    vague_reference = any(
        phrase in normalized
        for phrase in ("cai luc nay", "luc nay", "cai nay", "ngay do", "phien do", "hom do", "thi sao", "con")
    )
    parsed["is_followup_like"] = only_entity or only_date or comparative or vague_reference

    required_fields = ["intent", "topic"]
    if parsed.get("topic") not in ("market_wave", "stock_4key_screen"):
        required_fields.append("entities")
    for field in required_fields:
        if not parsed.get(field):
            parsed["missing_fields"].append(field)
    if parsed.get("intent") == "metric_lookup" and not parsed.get("metric"):
        parsed["missing_fields"].append("metric")

    return parsed


def state_has_enough_context(state: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(state, dict):
        return False
    if not state.get("intent") or not state.get("topic"):
        return False
    if state.get("intent") == "metric_lookup" and not state.get("metric"):
        return False
    if state.get("topic") in ("market_wave", "stock_4key_screen"):
        return True
    entities = state.get("entities") or []
    if not entities:
        return False
    return True


def compact_state(parsed: Dict[str, Any]) -> Dict[str, Any]:
    state: Dict[str, Any] = {}
    for key in ("intent", "topic", "metric", "entities", "time_context"):
        value = parsed.get(key)
        if value:
            state[key] = value
    return state


def merge_state(current: Dict[str, Any], previous: Dict[str, Any]) -> tuple[Dict[str, Any], List[str], List[str]]:
    merged = dict(previous or {})
    inherited: List[str] = []
    overridden: List[str] = []

    for key in ("intent", "topic", "metric"):
        if current.get(key):
            if merged.get(key) and merged.get(key) != current[key]:
                overridden.append(key)
            merged[key] = current[key]
        elif merged.get(key):
            inherited.append(key)

    current_entities = current.get("entities") or []
    previous_entities = previous.get("entities") or []
    if current.get("comparison_entity") and previous_entities:
        merged_entities = previous_entities[:]
        for entity in current_entities:
            if entity not in merged_entities:
                merged_entities.append(entity)
        merged["entities"] = merged_entities
        overridden.append("entities")
    elif current_entities:
        if previous_entities and previous_entities != current_entities:
            overridden.append("entities")
        merged["entities"] = current_entities
    elif previous_entities:
        inherited.append("entities")

    current_time = current.get("time_context")
    if current.get("time_relation"):
        current_time = apply_time_relation(previous.get("time_context"), current.get("time_relation"))
    if current_time:
        if previous.get("time_context") and previous.get("time_context") != current_time:
            overridden.append("time")
        merged["time_context"] = current_time
    elif previous.get("time_context"):
        inherited.append("time")

    return merged, sorted(set(inherited)), sorted(set(overridden))


def state_from_recent_messages(recent_messages: List[Dict[str, str]], now: datetime) -> Dict[str, Any]:
    state: Dict[str, Any] = {}
    for message in recent_messages or []:
        if message.get("role") != "user":
            continue
        parsed = parse_query(message.get("content") or "", now)
        parsed_state = compact_state(parsed)
        if state_has_enough_context(parsed_state):
            state = parsed_state
        elif parsed.get("is_followup_like") and state_has_enough_context(state):
            state, _, _ = merge_state(parsed, state)
    return state


def render_resolved_query(state: Dict[str, Any], fallback: str) -> str:
    entities = state.get("entities") or []
    entity_text = " và ".join(str(entity) for entity in entities if entity)
    date_text = display_date(state.get("time_context"))
    date_part = f" ngày {date_text}" if date_text and date_text != "hôm nay" else (" hôm nay" if date_text else "")
    intent = state.get("intent")
    topic = state.get("topic")
    metric = state.get("metric")
    normalized_fallback = normalize_text(fallback)

    if len(entities) >= 2 and topic == "cashflow":
        return f"So sánh dòng tiền {entity_text}{date_part}.".strip()
    if len(entities) >= 2 and metric:
        return f"So sánh {metric} {entity_text}{date_part}.".strip()
    if topic == "stock_4key_screen" and metric in FOUR_KEY_GROUP_LABELS:
        label = FOUR_KEY_GROUP_LABELS[metric]
        return f"Cung cấp danh mục {label}{date_part}.".strip()
    if intent == "metric_lookup" and topic == "market_wave" and metric in MARKET_WAVE_METRICS:
        label = MARKET_WAVE_METRICS[metric]["label"]
        prefix = f"{entity_text} " if entity_text else ""
        return f"{prefix}{label}{date_part} bao nhiêu?".strip()
    if intent == "metric_lookup" and metric and entity_text:
        metric_label = "giá" if metric == "price" else metric
        return f"{metric_label} {entity_text}{date_part} bao nhiêu?".strip()
    if topic == "cashflow" and entity_text:
        return f"Dòng tiền {entity_text}{date_part} thế nào?".strip()
    if topic == "stock_4key" and entity_text:
        if entity_text.lower() in (fallback or "").lower():
            return (fallback or "").strip()
        if any(cue in normalized_fallback for cue in STOCK_4KEY_DETAIL_CUES):
            return f"Vi sao {entity_text} thuoc nhom 4 Key{date_part}?".strip()
        return f"{entity_text} thuoc nhom 4 Key nao{date_part}?".strip()
    if topic == "stock_analysis" and entity_text:
        return f"Phân tích {entity_text}{date_part}.".strip()
    return (fallback or "").strip()


def resolve_conversation_context(
    current_query: str,
    conversation_state: Optional[Dict[str, Any]] = None,
    recent_messages: Optional[List[Dict[str, str]]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or datetime.now()
    current = parse_query(current_query, now)
    current_state = compact_state(current)

    if state_has_enough_context(current_state) and not current.get("is_followup_like"):
        resolved_query = render_resolved_query(current_state, current_query)
        return {
            "raw_query": current_query,
            "resolved_query": resolved_query,
            "is_followup": False,
            "need_more_context": False,
            "used_history": False,
            "history_source": None,
            "used_turns": 0,
            "inherited_fields": [],
            "overridden_fields": [],
            "confidence": 0.99,
            "next_state": current_state,
        }

    previous_state = conversation_state if state_has_enough_context(conversation_state) else None
    history_source = "state" if previous_state else None
    used_turns = 0

    if not previous_state and recent_messages:
        previous_state = state_from_recent_messages(recent_messages, now)
        if state_has_enough_context(previous_state):
            history_source = "recent_turns"
            used_turns = max(1, len([m for m in recent_messages if m.get("role") == "user"]))

    if current.get("is_followup_like") and state_has_enough_context(previous_state):
        merged, inherited, overridden = merge_state(current, previous_state or {})
        if state_has_enough_context(merged):
            resolved_query = render_resolved_query(merged, current_query)
            confidence = 0.97 if history_source == "state" else 0.89
            if current.get("time_relation"):
                confidence = min(confidence, 0.94)
            return {
                "raw_query": current_query,
                "resolved_query": resolved_query,
                "is_followup": True,
                "need_more_context": False,
                "used_history": True,
                "history_source": history_source,
                "used_turns": used_turns,
                "inherited_fields": inherited,
                "overridden_fields": overridden,
                "confidence": confidence,
                "next_state": merged,
            }

    if state_has_enough_context(current_state):
        resolved_query = render_resolved_query(current_state, current_query)
        return {
            "raw_query": current_query,
            "resolved_query": resolved_query,
            "is_followup": False,
            "need_more_context": False,
            "used_history": False,
            "history_source": None,
            "used_turns": 0,
            "inherited_fields": [],
            "overridden_fields": [],
            "confidence": 0.92,
            "next_state": current_state,
        }

    if current.get("is_followup_like"):
        return {
            "raw_query": current_query,
            "resolved_query": None,
            "is_followup": True,
            "need_more_context": True,
            "used_history": bool(history_source),
            "history_source": history_source,
            "used_turns": used_turns,
            "inherited_fields": [],
            "overridden_fields": [],
            "confidence": 0.41,
            "next_state": previous_state or {},
        }

    return {
        "raw_query": current_query,
        "resolved_query": (current_query or "").strip(),
        "is_followup": False,
        "need_more_context": False,
        "used_history": False,
        "history_source": None,
        "used_turns": 0,
        "inherited_fields": [],
        "overridden_fields": [],
        "confidence": 0.75,
        "next_state": current_state,
    }

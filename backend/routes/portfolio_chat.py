from __future__ import annotations

import os
import re
import unicodedata
from typing import Any, Callable, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from core.chat_runtime import collect_standard_chat
from core.context_resolver import STATE_TTL_MINUTES, compact_state, parse_query, state_has_enough_context
from core.model_router import pick_model
from core.orchestrator import format_stock_4key_answer, stock_4key_screen_args
from services.openai_client import current_token_usage, reset_token_usage


async def _save_direct_answer_turn(orchestrator: Any, user_id: str, question: str, answer: str) -> None:
    memory = getattr(orchestrator, "memory", None)
    if memory is None:
        return

    try:
        await memory.add(user_id, "user", question)
        await memory.add(user_id, "assistant", answer)
    except Exception as exc:
        print("PORTFOLIO_CHAT_MEMORY_SAVE_ERROR:", exc)

    if not hasattr(memory, "upsert_conversation_context_state"):
        return
    try:
        state = compact_state(parse_query(question))
        if state_has_enough_context(state):
            await memory.upsert_conversation_context_state(
                user_id=user_id,
                state=state,
                last_resolved_query=question.strip(),
                ttl_minutes=STATE_TTL_MINUTES,
            )
    except Exception as exc:
        print("PORTFOLIO_CHAT_CONTEXT_STATE_SAVE_ERROR:", exc)


class PortfolioChatIn(BaseModel):
    question: str
    portfolio: Optional[dict[str, Any]] = None
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    language: str = "vi"
    model: Optional[str] = None


router = APIRouter(prefix="/api", tags=["Portfolio Chat"])
_orchestrator_getter: Callable[[], Any] | None = None


def configure_portfolio_chat_api(orchestrator_getter: Callable[[], Any]):
    global _orchestrator_getter
    _orchestrator_getter = orchestrator_getter


def current_orchestrator():
    if not _orchestrator_getter:
        raise HTTPException(status_code=503, detail="AI service is not ready")

    orchestrator = _orchestrator_getter()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="AI service is not ready")

    return orchestrator


def require_portfolio_chat_api_key(x_api_key: Optional[str]):
    expected = os.getenv("PORTFOLIO_CHAT_API_KEY", "").strip()
    if expected and (x_api_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


def normalize_conversation_id(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return "default"
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "-", raw).strip("-.")
    if not cleaned:
        raise HTTPException(status_code=400, detail="conversation_id is invalid")
    return cleaned[:120]


def normalize_user_id(value: Optional[str]) -> str:
    raw = (value or "portfolio-user").strip()
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "-", raw).strip("-.")
    return (cleaned or "portfolio-user")[:120]


def build_chat_input(question: str, portfolio: Optional[dict[str, Any]] = None) -> tuple[str, bool]:
    return question.strip(), False

def normalize_search_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = normalized.replace("đ", "d").replace("Đ", "D")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


PORTFOLIO_4KEY_QUESTION_TO_CAT = {
    "ma nao dung song dung nganh": "dd",
    "ma nao dung song sai nganh": "ds",
    "ma nao sai song dung nganh": "sd",
    "ma nao dung nganh sai song": "sd",
    "ma nao sai song sai nganh": "ss",
}


def requested_portfolio_4key_cat(question: str) -> Optional[str]:
    return PORTFOLIO_4KEY_QUESTION_TO_CAT.get(normalize_search_text(question))



def requested_portfolio_4key_cat_fuzzy(question: str) -> Optional[str]:
    normalized = normalize_search_text(question)
    if "dung song" in normalized and "dung nganh" in normalized:
        return "dd"
    if "dung song" in normalized and "sai nganh" in normalized:
        return "ds"
    if "sai song" in normalized and "dung nganh" in normalized:
        return "sd"
    if "dung nganh" in normalized and "sai song" in normalized:
        return "sd"
    if "sai song" in normalized and "sai nganh" in normalized:
        return "ss"
    return None


def is_portfolio_4key_list_question(question: str) -> bool:
    normalized = normalize_search_text(question)
    if not requested_portfolio_4key_cat_fuzzy(question):
        return False
    return any(
        phrase in normalized
        for phrase in (
            "cung cap",
            "danh sach",
            "danh muc",
            "list",
            "liet ke",
            "cac ma",
            "nhung ma",
            "loc",
        )
    )


def is_portfolio_compare_question(question: str) -> bool:
    normalized = normalize_search_text(question)
    if not normalized:
        return False
    return (
        normalized == "so sanh"
        or normalized.startswith("so sanh ")
        or normalized == "compare"
        or normalized.startswith("compare ")
    )

def extract_portfolio_positions(portfolio: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(portfolio, dict):
        return []

    positions: list[dict[str, Any]] = []
    for key in ("positions", "items", "rows", "tickers", "data", "portfolio"):
        value = portfolio.get(key)
        if isinstance(value, list):
            positions.extend(item for item in value if isinstance(item, dict))

    position = portfolio.get("position")
    if isinstance(position, list):
        positions.extend(item for item in position if isinstance(item, dict))
    elif isinstance(position, dict):
        positions.append(position)

    if isinstance(portfolio.get("ticker"), str):
        positions.append(portfolio)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for position in positions:
        ticker = position_ticker(position)
        key = ticker or str(id(position))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(position)
    return deduped

def extract_portfolio_position(portfolio: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not isinstance(portfolio, dict):
        return None
    position = portfolio.get("position")
    if isinstance(position, dict):
        return position
    positions = portfolio.get("positions")
    if isinstance(positions, list) and positions and isinstance(positions[0], dict):
        return positions[0]
    if isinstance(portfolio.get("ticker"), str):
        return portfolio
    return None


def position_ticker(position: Optional[dict[str, Any]]) -> str:
    if not isinstance(position, dict):
        return ""
    return str(
        position.get("ticker")
        or position.get("symbol")
        or position.get("stockCode")
        or position.get("stock_code")
        or position.get("code")
        or position.get("key")
        or position.get("keyName")
        or ""
    ).strip().upper()


FOUR_KEY_GROUP_TO_CAT = {
    "dd": "dd",
    "ds": "ds",
    "sd": "sd",
    "ss": "ss",
    "dung song dung nganh": "dd",
    "dung song sai nganh": "ds",
    "dung nganh sai song": "sd",
    "sai song dung nganh": "sd",
    "sai song sai nganh": "ss",
}


def position_4key_cat(position: Optional[dict[str, Any]]) -> Optional[str]:
    if not isinstance(position, dict):
        return None
    raw = (
        position.get("cat")
        or position.get("group_4key")
        or position.get("group")
        or position.get("fourKey")
        or position.get("four_key")
        or position.get("status")
        or position.get("category")
    )
    return FOUR_KEY_GROUP_TO_CAT.get(normalize_search_text(str(raw or "")))


FOUR_KEY_CAT_LABELS = {
    "dd": "\u0111\u00fang s\u00f3ng \u0111\u00fang ng\u00e0nh",
    "ds": "\u0111\u00fang s\u00f3ng sai ng\u00e0nh",
    "sd": "sai s\u00f3ng \u0111\u00fang ng\u00e0nh",
    "ss": "sai s\u00f3ng sai ng\u00e0nh",
}


FOUR_KEY_CAT_PRIORITY = {
    "dd": 0,
    "ds": 1,
    "sd": 2,
    "ss": 3,
}


def _position_number(position: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = position.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _format_delta(value: Optional[float]) -> str:
    if value is None:
        return "-"
    formatted = f"{value:+.1f}"
    return formatted.rstrip("0").rstrip(".")


def position_stock_delta(position: dict[str, Any]) -> Optional[float]:
    current = _position_number(position, "smdt", "smdtCurrent", "stockSmdt")
    previous = _position_number(position, "smdtPrev", "smdtPrevious", "stockSmdtPrev")
    if current is None or previous is None:
        return None
    return current - previous


def position_branch_delta(position: dict[str, Any]) -> Optional[float]:
    current = _position_number(position, "branchSmdt", "industrySmdt")
    previous = _position_number(position, "branchSmdtPrev", "industrySmdtPrev")
    if current is None or previous is None:
        return None
    return current - previous


def _compare_sort_key(position: dict[str, Any]) -> tuple[float, float, float, str]:
    cat = position_4key_cat(position)
    stock_delta = position_stock_delta(position)
    branch_delta = position_branch_delta(position)
    return (
        FOUR_KEY_CAT_PRIORITY.get(cat or "", 99),
        -(stock_delta if stock_delta is not None else float("-inf")),
        -(branch_delta if branch_delta is not None else float("-inf")),
        position_ticker(position),
    )


def answer_portfolio_compare_4key(question: str, portfolio: Optional[dict[str, Any]]) -> Optional[str]:
    if not is_portfolio_compare_question(question):
        return None

    positions = [
        position
        for position in extract_portfolio_positions(portfolio)
        if position_ticker(position)
    ]
    if not positions:
        return "Vui l\u00f2ng g\u1eedi danh m\u1ee5c c\u00e1c m\u00e3 c\u1ea7n so s\u00e1nh."

    if len(positions) == 1:
        position = positions[0]
        ticker = position_ticker(position)
        cat = position_4key_cat(position)
        cat_label = FOUR_KEY_CAT_LABELS.get(cat or "", "ch\u01b0a c\u00f3 nh\u00f3m 4-key")
        return (
            f"Hi\u1ec7n ch\u1ec9 c\u00f3 1 m\u00e3 {ticker} trong danh m\u1ee5c g\u1eedi l\u00ean, "
            "ch\u01b0a \u0111\u1ee7 \u0111\u1ec3 so s\u00e1nh gi\u1eefa nhi\u1ec1u m\u00e3.\n"
            f"{ticker}: {cat_label}, \u0111\u1ed9ng l\u01b0\u1ee3ng m\u00e3 {_format_delta(position_stock_delta(position))}, "
            f"\u0111\u1ed9ng l\u01b0\u1ee3ng ng\u00e0nh {_format_delta(position_branch_delta(position))}."
        )

    ranked = sorted(positions, key=_compare_sort_key)
    lines = [
        "So s\u00e1nh c\u00e1c m\u00e3 trong danh m\u1ee5c theo 4-key:",
        "",
        "| M\u00e3 | Nh\u00f3m 4-key | \u0110\u1ed9ng l\u01b0\u1ee3ng m\u00e3 | \u0110\u1ed9ng l\u01b0\u1ee3ng ng\u00e0nh |",
        "|---|---|---:|---:|",
    ]
    for position in ranked:
        ticker = position_ticker(position)
        cat = position_4key_cat(position)
        cat_label = FOUR_KEY_CAT_LABELS.get(cat or "", "ch\u01b0a c\u00f3 nh\u00f3m 4-key")
        lines.append(
            f"| {ticker} | {cat_label} | {_format_delta(position_stock_delta(position))} | "
            f"{_format_delta(position_branch_delta(position))} |"
        )

    best = ranked[0]
    best_ticker = position_ticker(best)
    best_cat = position_4key_cat(best)
    best_label = FOUR_KEY_CAT_LABELS.get(best_cat or "", "c\u00f3 d\u1eef li\u1ec7u 4-key t\u1ed1t nh\u1ea5t trong danh m\u1ee5c")
    lines.extend([
        "",
        f"K\u1ebft lu\u1eadn: {best_ticker} \u0111ang \u0111\u1ee9ng \u0111\u1ea7u trong danh m\u1ee5c theo 4-key ({best_label}).",
    ])
    return "\n".join(lines)

def polish_portfolio_compare_answer(
    orchestrator: Any,
    question: str,
    base_answer: str,
    selected_model: Optional[str],
) -> tuple[str, dict[str, Any]]:
    oa = getattr(orchestrator, "oa", None)
    if oa is None:
        return base_answer, {}

    reset_token_usage()
    prompt = f"""
Cau hoi user:
{question}

Du lieu so sanh bat buoc dung, da tinh san:
{base_answer}

Yeu cau:
- Viet lai thanh cau tra loi tieng Viet tu nhien, de doc hon.
- Chi dung dung so lieu va thu tu trong du lieu tren, khong them ma moi, khong bia gia/volume/tin tuc.
- Khong khuyen nghi mua ban tuyet doi; chi noi ma nao noi bat hon theo 4-key.
- Neu co ma dung song dung nganh, neu ro ma do dang uu tien hon trong danh muc theo 4-key.
- Tra loi ngan gon, co the dung bullet ngan, khong can bang markdown.
""".strip()
    try:
        resp = oa.chat(
            model=pick_model(selected_model),
            messages=[
                {
                    "role": "system",
                    "content": "Ban la tro ly StockTraders AI. Tra loi tieng Viet tu nhien, ngan gon, bam sat so lieu duoc dua.",
                },
                {"role": "user", "content": prompt},
            ],
            tools=None,
            tool_choice="auto",
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or base_answer, current_token_usage()
    except Exception as exc:
        print("PORTFOLIO_COMPARE_POLISH_ERROR:", exc)
        return base_answer, current_token_usage()

def format_single_position_4key_answer(ticker: str, is_match: bool, requested_cat: str) -> str:
    if is_match:
        return ticker
    labels = {
        "dd": "đúng sóng đúng ngành",
        "ds": "đúng sóng sai ngành",
        "sd": "sai sóng đúng ngành",
        "ss": "sai sóng sai ngành",
    }
    label = labels.get(requested_cat, "nhóm 4 Key được hỏi")
    return f"Không có mã nào {label} trong mã được gửi."


def answer_portfolio_position_4key(question: str, portfolio: Optional[dict[str, Any]]) -> Optional[str]:
    requested_cat = requested_portfolio_4key_cat(question)
    if not requested_cat:
        return None

    position = extract_portfolio_position(portfolio)
    ticker = position_ticker(position)
    if not ticker:
        return "Vui lòng gửi mã cần phân tích."

    actual_cat = position_4key_cat(position)
    if actual_cat is None:
        return "Vui lòng gửi trạng thái 4 Key của mã cần phân tích."
    return format_single_position_4key_answer(ticker, actual_cat == requested_cat, requested_cat)


REASON_TRIGGER_PHRASES = ("tai sao", "vi sao", "sao lai", "ly do", "giai thich")


def is_portfolio_4key_reason_question(question: str) -> bool:
    normalized = normalize_search_text(question)
    if not any(phrase in normalized for phrase in REASON_TRIGGER_PHRASES):
        return False
    return requested_portfolio_4key_cat_fuzzy(question) is not None


def find_portfolio_position_by_question_ticker(
    question: str, portfolio: Optional[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    positions = extract_portfolio_positions(portfolio)
    if not positions:
        return None
    mentioned = set(re.findall(r"[A-Za-z]{2,5}", (question or "").upper()))
    for position in positions:
        ticker = position_ticker(position)
        if ticker and ticker in mentioned:
            return position
    return None


def format_portfolio_4key_reason_answer(
    ticker: str,
    actual_cat: Optional[str],
    claimed_cat: str,
    position: dict[str, Any],
) -> str:
    if actual_cat is None:
        return f"Chưa có đủ dữ liệu 4-key của {ticker} để xác nhận nhóm hiện tại."

    stock_delta_txt = _format_delta(position_stock_delta(position))
    branch_delta_txt = _format_delta(position_branch_delta(position))
    actual_label = FOUR_KEY_CAT_LABELS.get(actual_cat, "chưa rõ nhóm")

    if actual_cat != claimed_cat:
        claimed_label = FOUR_KEY_CAT_LABELS.get(claimed_cat, "nhóm được hỏi")
        return (
            f"{ticker} hiện KHÔNG ở trạng thái \"{claimed_label}\". "
            f"Theo dữ liệu 4-key hiện tại, {ticker} đang ở nhóm \"{actual_label}\" "
            f"(động lượng mã {stock_delta_txt}, động lượng ngành {branch_delta_txt})."
        )

    return (
        f"{ticker} đang ở nhóm \"{actual_label}\" vì động lượng SMDT của mã là {stock_delta_txt} "
        f"và động lượng SMDT của ngành là {branch_delta_txt}."
    )


def answer_portfolio_position_4key_reason(
    question: str, portfolio: Optional[dict[str, Any]]
) -> Optional[str]:
    if not is_portfolio_4key_reason_question(question):
        return None
    claimed_cat = requested_portfolio_4key_cat_fuzzy(question)
    if not claimed_cat:
        return None

    position = find_portfolio_position_by_question_ticker(question, portfolio)
    if position is None:
        return None

    ticker = position_ticker(position)
    actual_cat = position_4key_cat(position)
    return format_portfolio_4key_reason_answer(ticker, actual_cat, claimed_cat, position)



def answer_portfolio_list_4key(question: str, portfolio: Optional[dict[str, Any]]) -> Optional[str]:
    if not is_portfolio_4key_list_question(question):
        return None

    requested_cat = requested_portfolio_4key_cat_fuzzy(question)
    if not requested_cat:
        return None

    labels = {
        "dd": "đúng sóng đúng ngành",
        "ds": "đúng sóng sai ngành",
        "sd": "sai sóng đúng ngành",
        "ss": "sai sóng sai ngành",
    }
    label = labels.get(requested_cat, "nhóm 4 Key được hỏi")
    positions = extract_portfolio_positions(portfolio)
    if not positions:
        return None

    tickers = [
        position_ticker(position)
        for position in positions
        if position_ticker(position) and position_4key_cat(position) == requested_cat
    ]
    if not tickers:
        return f"Không có mã nào {label} trong danh mục hiện tại."
    return ", ".join(tickers)

def answer_market_4key_screen(orchestrator: Any, question: str) -> Optional[str]:
    args = stock_4key_screen_args(question)
    if not args:
        return None
    executor = getattr(orchestrator, "executor", None)
    if executor is None:
        return None
    result = executor.call(
        "getStock4KeyScreen",
        args,
        user_text=question,
    )
    return format_stock_4key_answer(result, user_text=question)


@router.post("/portfolio-chat")
async def portfolio_chat(
    payload: PortfolioChatIn,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
):
    require_portfolio_chat_api_key(x_api_key)

    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    conversation_id = normalize_conversation_id(payload.conversation_id)
    user_id = normalize_user_id(payload.user_id)
    chat_user_id = f"portfolio:{user_id}:{conversation_id}"
    user_text, _ = build_chat_input(question, payload.portfolio)
    orchestrator = current_orchestrator()

    direct_usage: dict[str, Any] = {}
    direct_answer = answer_portfolio_compare_4key(question, payload.portfolio)
    if direct_answer is not None and is_portfolio_compare_question(question):
        compare_positions = [
            position
            for position in extract_portfolio_positions(payload.portfolio)
            if position_ticker(position)
        ]
        if len(compare_positions) >= 2:
            direct_answer, direct_usage = polish_portfolio_compare_answer(
                orchestrator,
                question,
                direct_answer,
                payload.model,
            )
    if direct_answer is None:
        direct_answer = answer_market_4key_screen(orchestrator, question)
    if direct_answer is None:
        direct_answer = answer_portfolio_list_4key(question, payload.portfolio)
    if direct_answer is None:
        direct_answer = answer_portfolio_position_4key(question, payload.portfolio)
    if direct_answer is None:
        direct_answer = answer_portfolio_position_4key_reason(question, payload.portfolio)
    if direct_answer is not None:
        await _save_direct_answer_turn(orchestrator, chat_user_id, question, direct_answer)
        return {
            "answer": direct_answer,
            "sources": [],
            "usage": direct_usage,
            "conversation_id": conversation_id,
        }

    answer, done_data = await collect_standard_chat(
        orchestrator,
        user_id=chat_user_id,
        user_text=user_text,
        language=payload.language,
        selected_model=payload.model
    )

    return {
        "answer": answer,
        "sources": done_data.get("sources") or [],
        "usage": done_data.get("usage") or {},
        "conversation_id": conversation_id,
    }

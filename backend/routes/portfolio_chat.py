from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any, Callable, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from core.chat_runtime import collect_standard_chat


class PortfolioChatIn(BaseModel):
    question: str
    portfolio: dict[str, Any]
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    language: str = "vi"
    model: Optional[str] = None


router = APIRouter(prefix="/api", tags=["Portfolio Chat"])
_orchestrator_getter: Callable[[], Any] | None = None


PORTFOLIO_CONTEXT_PHRASES = (
    "4 key",
    "four key",
    "nhom 4 key",
    "composite",
    "composite score",
    "score",
    "diem composite",
    "diem tong",
    "rating",
    "xep hang",
    "danh gia tong hop",
    "phan tich co phieu",
    "phan tich ma",
    "danh gia co phieu",
    "danh gia ma",
    "ma nao dung song",
    "ma nao sai song",
    "dung song dung nganh",
    "dung song sai nganh",
    "sai song dung nganh",
    "sai song sai nganh",
)

NON_PORTFOLIO_DATA_PHRASES = (
    "dat chuan ma manh",
    "bat dau manh",
    "ma manh",
    "smdt",
    "suc manh dong tien",
    "gia",
    "gia hom nay",
    "tin hieu dong tien",
    "tin hieu mua ban",
    "mua ban",
    "dong tien",
    "cho mua",
    "cho ban",
)

STRONG_PORTFOLIO_PHRASES = (
    "4 key",
    "four key",
    "nhom 4 key",
    "composite",
    "composite score",
    "score",
    "diem composite",
    "diem tong",
    "rating",
    "xep hang",
    "danh gia tong hop",
)


FOUR_KEY_GROUP_BY_CAT = {
    "dd": "\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh",
    "ds": "\u0110\u00fang s\u00f3ng - Sai ng\u00e0nh",
    "sd": "Sai s\u00f3ng - \u0110\u00fang ng\u00e0nh",
    "ss": "Sai s\u00f3ng - Sai ng\u00e0nh",
}

SIMPLE_FOUR_KEY_PHRASES = (
    "4 key",
    "four key",
    "nhom 4 key",
    "thuoc nhom",
    "danh gia ma",
    "danh gia co phieu",
    "ma nao dung song",
    "ma nao sai song",
    "dung song dung nganh",
    "dung song sai nganh",
    "sai song dung nganh",
    "sai song sai nganh",
)

FOUR_KEY_DETAIL_PHRASES = (
    "vi sao",
    "tai sao",
    "ly do",
    "giai thich",
    "chi tiet",
    "phan tich",
    "composite",
    "score",
    "diem",
    "breakdown",
    "smdt",
    "suc manh dong tien",
    "dong luc",
    "gia",
    "bonus",
    "khuyen nghi",
)


REQUESTED_FOUR_KEY_GROUPS = (
    ("dung song dung nganh", FOUR_KEY_GROUP_BY_CAT["dd"]),
    ("dung song sai nganh", FOUR_KEY_GROUP_BY_CAT["ds"]),
    ("sai song dung nganh", FOUR_KEY_GROUP_BY_CAT["sd"]),
    ("sai song sai nganh", FOUR_KEY_GROUP_BY_CAT["ss"]),
)


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


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFD", value or "")
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = text.replace("Ä‘", "d").replace("Ä", "D")
    return re.sub(r"\s+", " ", text.lower()).strip()


def should_use_portfolio_context(question: str) -> bool:
    normalized = normalize_text(question)
    has_portfolio_signal = any(phrase in normalized for phrase in PORTFOLIO_CONTEXT_PHRASES)
    if not has_portfolio_signal:
        return False
    has_strong_portfolio_signal = any(phrase in normalized for phrase in STRONG_PORTFOLIO_PHRASES)
    has_regular_data_signal = any(phrase in normalized for phrase in NON_PORTFOLIO_DATA_PHRASES)
    return has_strong_portfolio_signal or not has_regular_data_signal


def is_simple_four_key_question(question: str) -> bool:
    normalized = normalize_text(question)
    if not should_use_portfolio_context(question):
        return False
    if any(phrase in normalized for phrase in FOUR_KEY_DETAIL_PHRASES):
        return False
    return any(phrase in normalized for phrase in SIMPLE_FOUR_KEY_PHRASES)


def requested_four_key_group(question: str) -> str | None:
    normalized = normalize_text(question)
    for phrase, group in REQUESTED_FOUR_KEY_GROUPS:
        if phrase in normalized:
            return group
    return None


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def iter_positions(portfolio: dict[str, Any]) -> list[dict[str, Any]]:
    positions = portfolio.get("positions")
    if not isinstance(positions, list):
        return []
    return [item for item in positions if isinstance(item, dict)]


def find_requested_position(question: str, portfolio: dict[str, Any]) -> dict[str, Any] | None:
    positions = iter_positions(portfolio)
    if len(positions) == 1:
        return positions[0]

    for position in positions:
        ticker = str(position.get("ticker") or "").strip()
        if ticker and re.search(rf"\b{re.escape(ticker)}\b", question, flags=re.IGNORECASE):
            return position
    return None


def derive_four_key_group(position: dict[str, Any]) -> str | None:
    cat = str(position.get("cat") or position.get("group") or "").strip().lower()
    if cat in FOUR_KEY_GROUP_BY_CAT:
        return FOUR_KEY_GROUP_BY_CAT[cat]

    smdt = as_float(position.get("smdt"))
    smdt_prev = as_float(position.get("smdtPrev"))
    branch_smdt = as_float(position.get("branchSmdt"))
    branch_smdt_prev = as_float(position.get("branchSmdtPrev"))
    if None in (smdt, smdt_prev, branch_smdt, branch_smdt_prev):
        return None

    ticker_key = "d" if smdt > smdt_prev else "s"
    branch_key = "d" if branch_smdt > branch_smdt_prev else "s"
    return FOUR_KEY_GROUP_BY_CAT.get(f"{ticker_key}{branch_key}")


def build_simple_four_key_answer(question: str, portfolio: dict[str, Any]) -> str | None:
    if not is_simple_four_key_question(question):
        return None

    position = find_requested_position(question, portfolio)
    if not position:
        return None

    group = derive_four_key_group(position)
    if not group:
        return None

    requested_group = requested_four_key_group(question)
    if requested_group:
        if group == requested_group:
            return f"C\u00f3, m\u00e3 n\u00e0y \u0111ang thu\u1ed9c nh\u00f3m \"{group}\"."
        return f"Kh\u00f4ng, m\u00e3 n\u00e0y \u0111ang thu\u1ed9c nh\u00f3m \"{group}\"."

    return f"Nh\u00f3m 4 Key: \"{group}\""


def build_portfolio_chat_text(question: str, portfolio: dict[str, Any]) -> str:
    portfolio_json = json.dumps(portfolio, ensure_ascii=False, separators=(",", ":"))
    as_of_date = str(portfolio.get("asOfDate") or portfolio.get("date") or "").strip()
    date_rule = (
        f"Ng\u00e0y \u0111\u00e1nh gi\u00e1 b\u1eaft bu\u1ed9c l\u00e0 {as_of_date}; kh\u00f4ng \u0111\u01b0\u1ee3c t\u1ef1 \u0111\u1ed5i sang ng\u00e0y hi\u1ec7n t\u1ea1i. "
        if as_of_date else ""
    )
    return (
        "Ng\u1eef c\u1ea3nh danh m\u1ee5c hi\u1ec7n t\u1ea1i do frontend/backend web cung c\u1ea5p. "
        "H\u00e3y tr\u1ea3 l\u1eddi c\u00f9ng phong c\u00e1ch v\u00e0 quy t\u1eafc nh\u01b0 web chat StockTraders AI. "
        "B\u1eaft bu\u1ed9c tr\u1ea3 l\u1eddi b\u1eb1ng ti\u1ebfng Vi\u1ec7t \u0111\u1ea7y \u0111\u1ee7 d\u1ea5u, kh\u00f4ng d\u00f9ng nh\u00e3n kh\u00f4ng d\u1ea5u nh\u01b0 Dung song/Dung nganh/tin hieu. "
        "\u0110\u00e2y l\u00e0 request c\u00f3 k\u00e8m d\u1eef li\u1ec7u portfolio, ph\u1ea3i tr\u1ea3 l\u1eddi tr\u1ef1c ti\u1ebfp, kh\u00f4ng h\u1ecfi l\u1ea1i v\u00e0 kh\u00f4ng g\u1ee3i \u00fd danh s\u00e1ch c\u00e2u h\u1ecfi. "
        f"{date_rule}"
        "N\u1ebfu user ch\u1ec9 h\u1ecfi m\u00e3 thu\u1ed9c nh\u00f3m 4 key n\u00e0o v\u00e0 kh\u00f4ng h\u1ecfi v\u00ec sao/l\u00fd do/chi ti\u1ebft/ph\u00e2n t\u00edch/score, ch\u1ec9 tr\u1ea3 l\u1eddi \u0111\u00fang m\u1ed9t d\u00f2ng: Nh\u00f3m 4 Key: \"<t\u00ean nh\u00f3m>\". "
        "Ch\u1ec9 gi\u1ea3i th\u00edch th\u00eam khi user h\u1ecfi v\u00ec sao, l\u00fd do, chi ti\u1ebft, ph\u00e2n t\u00edch, score ho\u1eb7c composite. "
        "Portfolio l\u00e0 ng\u1eef c\u1ea3nh \u01b0u ti\u00ean khi c\u00e2u h\u1ecfi n\u00f3i v\u1ec1 ph\u00e2n t\u00edch 4 key/composite/score c\u1ee7a c\u00e1c m\u00e3 trong danh m\u1ee5c. "
        "C\u00e1c case d\u1eef li\u1ec7u th\u00f4ng th\u01b0\u1eddng nh\u01b0 \u0111\u1ea1t chu\u1ea9n m\u00e3 m\u1ea1nh, SMDT, gi\u00e1, t\u00edn hi\u1ec7u, mua b\u00e1n kh\u00f4ng ph\u1ee5 thu\u1ed9c portfolio. "
        "Kh\u00f4ng b\u1ecba th\u00eam gi\u00e1, SMDT, t\u1ef7 tr\u1ecdng, hay m\u00e3 ngo\u00e0i d\u1eef li\u1ec7u n\u1ebfu c\u1ea3 portfolio v\u00e0 tool/API \u0111\u1ec1u kh\u00f4ng c\u00f3. "
        "N\u1ebfu position c\u00f3 cat th\u00ec d\u00f9ng cat \u0111\u1ec3 \u0111\u1ecdc nh\u00f3m 4 key: dd=\u0110\u00fang s\u00f3ng-\u0110\u00fang ng\u00e0nh, ds=\u0110\u00fang s\u00f3ng-Sai ng\u00e0nh, sd=Sai s\u00f3ng-\u0110\u00fang ng\u00e0nh, ss=Sai s\u00f3ng-Sai ng\u00e0nh. "
        "N\u1ebfu kh\u00f4ng c\u00f3 cat nh\u01b0ng c\u00f3 smdt/smdtPrev/branchSmdt/branchSmdtPrev th\u00ec ph\u1ea3i \u0111\u00e1nh gi\u00e1 tr\u1ef1c ti\u1ebfp t\u1eeb portfolio: SMDT m\u00e3 t\u0103ng l\u00e0 m\u00e3 \u0111\u00fang s\u00f3ng, SMDT ng\u00e0nh t\u0103ng l\u00e0 ng\u00e0nh \u0111\u00fang s\u00f3ng. "
        "N\u1ebfu portfolio \u0111\u00e3 \u0111\u1ee7 d\u1eef li\u1ec7u smdt/smdtPrev/branchSmdt/branchSmdtPrev cho m\u00e3 \u0111\u01b0\u1ee3c h\u1ecfi th\u00ec kh\u00f4ng c\u1ea7n l\u1ea5y d\u1eef li\u1ec7u ngo\u00e0i \u0111\u1ec3 \u0111\u1ed5i ng\u00e0y \u0111\u00e1nh gi\u00e1.\n\n"
        "Portfolio JSON:\n"
        f"{portfolio_json}\n\n"
        "C\u00e2u h\u1ecfi c\u1ee7a user:\n"
        f"{question.strip()}"
    )

def build_chat_input(question: str, portfolio: dict[str, Any]) -> tuple[str, bool]:
    if should_use_portfolio_context(question):
        return build_portfolio_chat_text(question, portfolio), True
    return question.strip(), False


@router.post("/portfolio-chat")
async def portfolio_chat(
    payload: PortfolioChatIn,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
):
    require_portfolio_chat_api_key(x_api_key)

    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if not isinstance(payload.portfolio, dict) or not payload.portfolio:
        raise HTTPException(status_code=400, detail="portfolio is required")

    conversation_id = normalize_conversation_id(payload.conversation_id)
    user_id = normalize_user_id(payload.user_id)
    chat_user_id = f"portfolio:{user_id}:{conversation_id}"
    simple_answer = build_simple_four_key_answer(question, payload.portfolio)
    if simple_answer:
        return {
            "answer": simple_answer,
            "sources": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "conversation_id": conversation_id,
        }

    user_text, uses_portfolio_context = build_chat_input(question, payload.portfolio)

    answer, done_data = await collect_standard_chat(
        current_orchestrator(),
        user_id=chat_user_id,
        user_text=user_text,
        language=payload.language,
        selected_model=payload.model,
        skip_question_guide=uses_portfolio_context,
    )

    return {
        "answer": answer,
        "sources": done_data.get("sources") or [],
        "usage": done_data.get("usage") or {},
        "conversation_id": conversation_id,
    }
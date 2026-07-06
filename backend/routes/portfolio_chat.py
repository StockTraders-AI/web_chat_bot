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
    return f"Nh\u00f3m 4 Key: \"{group}\""


def build_portfolio_chat_text(question: str, portfolio: dict[str, Any]) -> str:
    portfolio_json = json.dumps(portfolio, ensure_ascii=False, separators=(",", ":"))
    as_of_date = str(portfolio.get("asOfDate") or portfolio.get("date") or "").strip()
    date_rule = (
        f"Ngay danh gia bat buoc la {as_of_date}; khong duoc tu doi sang ngay hien tai. "
        if as_of_date else ""
    )
    return (
        "Ngu canh danh muc hien tai do frontend/backend web cung cap. "
        "Hay tra loi cung phong cach va quy tac nhu web chat StockTraders AI. "
        "Day la request co kem du lieu portfolio, phai tra loi truc tiep, khong hoi lai va khong goi y danh sach cau hoi. "
        f"{date_rule}"
        "Neu user chi hoi ma thuoc nhom 4 key nao va khong hoi vi sao/ly do/chi tiet/phan tich/score, chi tra loi dung mot dong: Nhom 4 Key: \"<ten nhom>\". "
        "Chi giai thich them khi user hoi vi sao, ly do, chi tiet, phan tich, score hoac composite. "
        "Portfolio la ngu canh uu tien khi cau hoi noi ve phan tich 4 key/composite/score cua cac ma trong danh muc. "
        "Cac case du lieu thong thuong nhu dat chuan ma manh, smdt, gia, tin hieu, mua ban khong phu thuoc portfolio. "
        "Khong bia them gia, SMDT, ty trong, hay ma ngoai du lieu neu ca portfolio va tool/API deu khong co. "
        "Neu position co cat thi dung cat de doc nhom 4 key: dd=Dung song-Dung nganh, ds=Dung song-Sai nganh, sd=Sai song-Dung nganh, ss=Sai song-Sai nganh. "
        "Neu khong co cat nhung co smdt/smdtPrev/branchSmdt/branchSmdtPrev thi phai danh gia truc tiep tu portfolio: smdt tang la ma dung song, branchSmdt tang la nganh dung song. "
        "Neu portfolio da du du lieu smdt/smdtPrev/branchSmdt/branchSmdtPrev cho ma duoc hoi thi khong can lay du lieu ngoai de doi ngay danh gia.\n\n"
        "Portfolio JSON:\n"
        f"{portfolio_json}\n\n"
        "Cau hoi cua user:\n"
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
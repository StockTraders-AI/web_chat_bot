from __future__ import annotations

import os
import re
import unicodedata
from typing import Any, Callable, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from core.chat_runtime import collect_standard_chat


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
    return str(position.get("ticker") or position.get("symbol") or position.get("stockCode") or "").strip().upper()


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
    raw = position.get("cat") or position.get("group_4key") or position.get("group")
    return FOUR_KEY_GROUP_TO_CAT.get(normalize_search_text(str(raw or "")))


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

    direct_answer = answer_portfolio_position_4key(question, payload.portfolio)
    if direct_answer is not None:
        return {
            "answer": direct_answer,
            "sources": [],
            "usage": {},
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

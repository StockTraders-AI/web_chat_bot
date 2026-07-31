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


def is_portfolio_4key_list_question(question: str) -> bool:
    return normalize_search_text(question) == "ma nao dung song dung nganh"


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


def position_is_right_wave_branch(position: Optional[dict[str, Any]]) -> Optional[bool]:
    if not isinstance(position, dict):
        return None
    raw = position.get("cat") or position.get("group_4key") or position.get("group")
    normalized = normalize_search_text(str(raw or ""))
    if normalized in {"dd", "dung song dung nganh"}:
        return True
    if normalized in {"ds", "sd", "ss", "dung song sai nganh", "dung nganh sai song", "sai song dung nganh", "sai song sai nganh"}:
        return False
    return None


def format_single_position_4key_answer(ticker: str, is_match: bool) -> str:
    if is_match:
        return ticker
    return "Không có mã nào đúng sóng đúng ngành trong mã được gửi."


def answer_portfolio_position_4key(question: str, portfolio: Optional[dict[str, Any]]) -> Optional[str]:
    if not is_portfolio_4key_list_question(question):
        return None

    position = extract_portfolio_position(portfolio)
    ticker = position_ticker(position)
    if not ticker:
        return "Vui lòng gửi mã cần phân tích."

    local_match = position_is_right_wave_branch(position)
    if local_match is None:
        return "Vui lòng gửi trạng thái 4 Key của mã cần phân tích."
    return format_single_position_4key_answer(ticker, local_match)


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

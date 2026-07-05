from __future__ import annotations

import json
import os
import re
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


def build_portfolio_chat_text(question: str, portfolio: dict[str, Any]) -> str:
    portfolio_json = json.dumps(portfolio, ensure_ascii=False, separators=(",", ":"))
    return (
        "Ngu canh danh muc hien tai do frontend/backend web cung cap. "
        "Hay tra loi cung phong cach va quy tac nhu web chat StockTraders AI. "
        "Day la request da co du lieu portfolio, phai tra loi truc tiep, khong hoi lai va khong goi y danh sach cau hoi. "
        "Khi cau hoi noi ve danh muc, chi su dung du lieu portfolio ben duoi; "
        "khong bia them gia, SMDT, ty trong, hay ma ngoai danh muc neu portfolio khong co. "
        "Neu position co cat thi dung cat de doc nhom 4 key: dd=Dung song-Dung nganh, ds=Dung song-Sai nganh, sd=Sai song-Dung nganh, ss=Sai song-Sai nganh. "
        "Neu khong co cat nhung co smdt/smdtPrev/branchSmdt/branchSmdtPrev thi tu suy ra: smdt tang la ma dung song, branchSmdt tang la nganh dung song.\n\n"
        "Portfolio JSON:\n"
        f"{portfolio_json}\n\n"
        "Cau hoi cua user:\n"
        f"{question.strip()}"
    )


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

    answer, done_data = await collect_standard_chat(
        current_orchestrator(),
        user_id=chat_user_id,
        user_text=build_portfolio_chat_text(question, payload.portfolio),
        language=payload.language,
        selected_model=payload.model,
    )

    return {
        "answer": answer,
        "sources": done_data.get("sources") or [],
        "usage": done_data.get("usage") or {},
        "conversation_id": conversation_id,
    }
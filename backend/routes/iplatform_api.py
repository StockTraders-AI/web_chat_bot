import os
import re
import uuid
from typing import Any, Callable, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel


class IPlatformChatIn(BaseModel):
    content: str
    conversation_id: Optional[str] = None
    language: str = "vi"
    model: Optional[str] = None


router = APIRouter(prefix="/api/ai", tags=["iPlatform"])
_orchestrator_getter: Callable[[], Any] | None = None


def configure_iplatform_api(orchestrator_getter: Callable[[], Any]):
    global _orchestrator_getter
    _orchestrator_getter = orchestrator_getter


def current_orchestrator():
    if not _orchestrator_getter:
        raise HTTPException(status_code=503, detail="AI service is not ready")

    orchestrator = _orchestrator_getter()
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="AI service is not ready")

    return orchestrator


def require_iplatform_api_key(x_api_key: Optional[str]):
    expected = os.getenv("IPLATFORM_API_KEY", "").strip()
    if expected and (x_api_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


def normalize_conversation_id(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return uuid.uuid4().hex
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "-", raw).strip("-.")
    if not cleaned:
        raise HTTPException(status_code=400, detail="conversation_id is invalid")
    return cleaned[:120]


@router.post("/chat")
async def iplatform_ai_chat(
    payload: IPlatformChatIn,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
):
    require_iplatform_api_key(x_api_key)

    content = (payload.content or "").strip()

    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    conversation_id = normalize_conversation_id(payload.conversation_id)
    answer_parts = []
    done_data = {}

    async for event, data in current_orchestrator().chat_stream(
        user_id=f"iplatform:{conversation_id}",
        user_text=content,
        language=(payload.language or "vi").strip() or "vi",
        selected_model=payload.model,
    ):
        if event == "delta":
            answer_parts.append(str(data.get("text") or ""))
        elif event == "done":
            done_data = data or {}

    return {
        "ok": True,
        "conversation_id": conversation_id,
        "answer": "".join(answer_parts).strip(),
        "sources": done_data.get("sources") or [],
    }


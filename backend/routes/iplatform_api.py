import os
from typing import Any, Callable, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel


class IPlatformChatIn(BaseModel):
    content: str


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


@router.post("/chat")
async def iplatform_ai_chat(
    payload: IPlatformChatIn,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
):
    require_iplatform_api_key(x_api_key)

    content = (payload.content or "").strip()

    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    answer_parts = []

    async for event, data in current_orchestrator().chat_stream(
        user_id="iplatform:default",
        user_text=content,
        language="vi",
        selected_model=None,
    ):
        if event == "delta":
            answer_parts.append(str(data.get("text") or ""))

    return {
        "ok": True,
        "answer": "".join(answer_parts).strip(),
    }


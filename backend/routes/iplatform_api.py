import os
import re
import uuid
from typing import Any, Callable, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.iplatform_auth import create_account_access_token, verify_iplatform_jwt
from core.quota import QuotaExceeded, QuotaService


class IPlatformChatIn(BaseModel):
    content: str
    conversation_id: Optional[str] = None
    language: str = "vi"
    model: Optional[str] = None


class IPlatformLoginIn(BaseModel):
    username: str
    password: str


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


def require_bearer_token(authorization: Optional[str]) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Missing Bearer JWT")
    return token.strip()


def normalize_conversation_id(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return "default"
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "-", raw).strip("-.")
    if not cleaned:
        raise HTTPException(status_code=400, detail="conversation_id is invalid")
    return cleaned[:120]


@router.post("/auth/login")
async def iplatform_auth_login(
    payload: IPlatformLoginIn,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
):
    require_iplatform_api_key(x_api_key)

    username = (payload.username or "").strip()
    if not username or not payload.password:
        raise HTTPException(status_code=400, detail="username and password are required")

    account = await current_orchestrator().memory.authenticate_account(
        username,
        payload.password,
    )
    if not account:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    try:
        token = create_account_access_token(account)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "ok": True,
        "access_token": token["access_token"],
        "token_type": "Bearer",
        "expires_in": token["expires_in"],
        "expires_at": token["expires_at"],
        "account": {
            "id": account.get("id"),
            "username": account.get("username"),
            "display_name": account.get("display_name"),
            "role": account.get("role"),
            "status": account.get("status"),
        },
    }


@router.post("/chat")
async def iplatform_ai_chat(
    payload: IPlatformChatIn,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
):
    require_iplatform_api_key(x_api_key)

    try:
        identity = verify_iplatform_jwt(require_bearer_token(authorization))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    content = (payload.content or "").strip()

    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    conversation_id = normalize_conversation_id(payload.conversation_id)
    request_id = uuid.uuid4().hex
    orchestrator = current_orchestrator()
    quota = QuotaService(orchestrator.memory)

    try:
        await quota.check_quota(identity.tenant_id, identity.user_id)
    except QuotaExceeded as exc:
        return JSONResponse(
            status_code=429,
            content={
                "ok": False,
                "code": exc.code,
                "message": exc.message,
                "retry_at": exc.usage.get("retry_5h_at") if exc.code == "QUOTA_5H_EXCEEDED" else exc.usage.get("retry_7d_at"),
                "retry_after_seconds": exc.retry_after_seconds,
                "usage": exc.usage,
            },
        )

    answer_parts = []
    done_data = {}
    chat_user_id = f"{identity.user_key}:{conversation_id}"

    async for event, data in orchestrator.chat_stream(
        user_id=chat_user_id,
        user_text=content,
        language=(payload.language or "vi").strip() or "vi",
        selected_model=payload.model,
    ):
        if event == "delta":
            answer_parts.append(str(data.get("text") or ""))
        elif event == "done":
            done_data = data or {}

    answer = "".join(answer_parts).strip()
    usage_summary = await quota.record_usage(
        tenant_id=identity.tenant_id,
        user_id=identity.user_id,
        user_key=identity.user_key,
        conversation_id=conversation_id,
        request_id=request_id,
        route="api/ai/chat",
        model=payload.model,
        usage=done_data.get("usage") or {},
        prompt_text=content,
        answer_text=answer,
    )

    return {
        "ok": True,
        "request_id": request_id,
        "tenant_id": identity.tenant_id,
        "user_id": identity.user_id,
        "conversation_id": conversation_id,
        "answer": answer,
        "sources": done_data.get("sources") or [],
        "usage": usage_summary,
    }



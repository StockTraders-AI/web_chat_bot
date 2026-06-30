import json, os
from datetime import datetime
from dotenv import load_dotenv
from fastapi import Cookie, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from core.condition_engine import (
    build_demo_flow_message,
    build_demo_flow_ai_messages,
    evaluate_flow_expression,
    resolve_flow_condition_refs,
    resolve_template_support,
    run_condition,
)

from settings import (
    ensure_dirs,
    ALLOWED_MODELS,
    DEFAULT_MODEL,
    AUTH_COOKIE_NAME,
    AUTH_COOKIE_SAMESITE,
    AUTH_COOKIE_SECURE,
    AUTH_SESSION_DAYS,
)
from core.memory import MemoryStore
from core.rag import RAGStore
from core.tool_engine import ToolRegistry
from core.orchestrator import Orchestrator
from core.sales_discovery import OPENING_MESSAGE, SalesDiscovery, is_explainer_target
from core.model_router import pick_model
from core.quota import QuotaService
from routes.iplatform_api import configure_iplatform_api, router as iplatform_router
from services.openai_client import OpenAIClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
app = FastAPI(title="StockTraders AI Chat")
app.include_router(iplatform_router)

DEFAULT_BLOCKED_IPS = {"185.177.72.205"}
BLOCKED_IPS = {
    ip.strip()
    for ip in os.getenv("BLOCKED_IPS", "").split(",")
    if ip.strip()
} | DEFAULT_BLOCKED_IPS


def get_request_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


@app.middleware("http")
async def block_bad_ips(request: Request, call_next):
    client_ip = get_request_ip(request)
    if client_ip in BLOCKED_IPS:
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    return await call_next(request)

# allow frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

memory = MemoryStore()
rag = RAGStore()
registry = ToolRegistry()
orch: Orchestrator | None = None
sales: SalesDiscovery | None = None
class ChatIn(BaseModel):
    user_id: str
    message: str
    language: str = "vi"
    model: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None  # reserved


class ProfileIn(BaseModel):
    gender: str
    birth_year: str
    investment_experience: str

class LoginIn(BaseModel):
    username: str
    password: str

class AccountCreateIn(BaseModel):
    username: str
    display_name: str
    password: str
    role: str

class AccountUpdateIn(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None

class DirectConditionTestIn(BaseModel):
    condition_key: str
    date: Optional[str] = None
    ticker: Optional[str] = None
class ResetPasswordIn(BaseModel):
    password: str

class AccountPermissionsIn(BaseModel):
    permissions: list[str]
class ConditionTemplateIn(BaseModel):
    type: str
    name: str
    condition_logic: str
    description: str
class ConditionTemplateUpdateIn(BaseModel):
    type: str
    name: str
    condition_logic: str
    description: str

class ConditionTypeIn(BaseModel):
    label: str

class ConditionTestIn(BaseModel):
    context: Dict[str, Any] = {}


class ConditionFlowDemoCheckIn(BaseModel):
    context: Dict[str, Any] = {}


class ConditionFlowActiveIn(BaseModel):
    active: bool


class ConditionFlowTriggerPromptIn(BaseModel):
    trigger_prompt: str = ""


class ConditionFlowIn(BaseModel):
    name: str
    expression: str
    prompt_template: str
    trigger_prompt: str = ""
    status: str = "draft"


class ConditionFlowUpdateIn(BaseModel):
    name: str
    expression: str
    prompt_template: str
    trigger_prompt: str = ""
    status: str = "draft"


class CaseIdeaIn(BaseModel):
    name: str
    indicators: str = ""
    description: str = ""


class SalesDiscoveryTargetIn(BaseModel):
    target_key: str = ""
    name: str
    description: str = ""
    suggested_question: str = ""
    recognizer_key: str = ""
    status: str = "waiting"
    active: bool = False


class SalesDiscoveryTargetReorderIn(BaseModel):
    direction: str

def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

def auth_token(authorization: Optional[str], session_cookie: Optional[str]) -> str:
    if session_cookie:
        return session_cookie.strip()

    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return token.strip()

    raise HTTPException(status_code=401, detail="Phien dang nhap khong hop le")

def set_auth_cookie(response: Response, token: str):
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=AUTH_SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
        path="/",
    )

def clear_auth_cookie(response: Response):
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
    )

async def current_account(authorization: Optional[str], session_cookie: Optional[str]):
    token = auth_token(authorization, session_cookie)
    account = await memory.get_account_by_session_token(token)
    if not account:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập không hợp lệ")

    return account

async def require_super_admin(authorization: Optional[str], session_cookie: Optional[str]):
    account = await current_account(authorization, session_cookie)
    if account["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Chỉ Super Admin mới có quyền thao tác")

    return account

async def require_admin_or_super_admin(authorization: Optional[str], session_cookie: Optional[str]):
    account = await current_account(authorization, session_cookie)
    if account["role"] not in {"admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="Chi Admin hoac Super Admin moi co quyen thao tac")

    return account


async def account_response(account: dict):
    effective = await memory.get_effective_permissions(account["id"])
    permissions = effective["permissions"] if effective else []
    return {**account, "permissions": permissions}

async def require_optional_permission(
    authorization,
    session_cookie,
):
    try:
        return await current_account(
            authorization,
            session_cookie
        )
    except:
        return None


async def resolve_valid_flow_refs(expression: str):
    templates = await memory.list_condition_templates()
    return resolve_flow_condition_refs(expression, templates)


def flow_refs_expression(refs: list[dict]) -> str:
    parts = []

    for index, ref in enumerate(refs):
        if index > 0:
            parts.append(ref.get("operator") or "AND")
        parts.append(str(ref["id"]))

    return " ".join(parts)


def build_demo_flow_ai_message(
    flow_name: str,
    condition_results: list[dict],
    trigger_prompt: str | None,
    check_date: str | None,
) -> str:
    fallback_message = build_demo_flow_message(
        flow_name,
        condition_results,
        trigger_prompt=None,
        check_date=check_date,
    )

    if not trigger_prompt or not trigger_prompt.strip():
        return fallback_message

    try:
        client = OpenAIClient()
        resp = client.chat(
            model=DEFAULT_MODEL,
            messages=build_demo_flow_ai_messages(
                flow_name=flow_name,
                condition_results=condition_results,
                trigger_prompt=trigger_prompt,
                check_date=check_date,
            ),
            tools=None,
            tool_choice="auto",
        )
        message = (resp.choices[0].message.content or "").strip()

        return message or fallback_message
    except Exception as exc:
        print("DEMO_FLOW_AI_MESSAGE_ERROR:", exc)
        return fallback_message


def template_condition_key(template: dict) -> str:
    return " ".join([
        str(template.get("name") or "").strip(),
        str(template.get("condition_logic") or "").strip(),
    ]).strip()


def make_sales_target_key(name: str) -> str:
    raw = "".join(
        char.lower() if char.isalnum() else "_"
        for char in (name or "").strip()
    )
    compact = "_".join(part for part in raw.split("_") if part)
    return compact or f"target_{int(datetime.now().timestamp())}"


def normalize_chat_text(text: str) -> str:
    import unicodedata
    import re

    normalized = unicodedata.normalize("NFD", text or "")
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = normalized.lower()
    return re.sub(r"\s+", " ", normalized).strip()


def is_affirmative_reply(text: str) -> bool:
    normalized = normalize_chat_text(text)
    return normalized in {
        "ok",
        "oki",
        "ok lam di",
        "duoc",
        "duoc roi",
        "co",
        "co chu",
        "muon",
        "lam di",
        "noi di",
        "giai thich di",
        "thuyet minh di",
        "vang",
        "uh",
        "u",
    }


def is_negative_reply(text: str) -> bool:
    normalized = normalize_chat_text(text)
    return normalized in {
        "khong",
        "ko",
        "k",
        "thoi",
        "bo qua",
        "khong can",
        "ko can",
    }


def next_pending_target_config(state: dict) -> dict | None:
    targets = state.get("targets") or {}
    configs = state.get("target_configs") or []

    for config in configs:
        key = config.get("target_key")
        if not key:
            continue
        if targets.get(key, {}).get("status") != "complete":
            return config

    return None


def pending_explainer_target(state: dict) -> dict | None:
    config = next_pending_target_config(state)
    if config and is_explainer_target(config):
        return config

    return None


def sales_state_completed(targets: dict, configs: list[dict]) -> bool:
    for config in configs or []:
        key = config.get("target_key")
        if key and targets.get(key, {}).get("status") != "complete":
            return False

    return True


@app.on_event("startup")
async def startup():
    global orch, sales
    ensure_dirs()
    await memory.init()
    registry.load()
    rag.load()
    orch = Orchestrator(memory=memory, rag=rag, registry=registry)
    configure_iplatform_api(lambda: orch)
    sales = SalesDiscovery(memory=memory)

@app.get("/meta/models")
def meta_models():
    return {"models": ALLOWED_MODELS}

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.post("/auth/login")
async def auth_login(payload: LoginIn, response: Response):
    account = await memory.authenticate_account(payload.username, payload.password)
    if not account:
        raise HTTPException(status_code=401, detail="Sai tài khoản hoặc mật khẩu")

    session = await memory.create_account_session(account["id"])
    set_auth_cookie(response, session["token"])
    return {
        "expires_at": session["expires_at"],
        "account": await account_response(account),
    }

@app.post("/auth/logout")
async def auth_logout(
    response: Response,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    token = auth_token(authorization, session_cookie)
    await memory.revoke_account_session(token)
    clear_auth_cookie(response)
    return {"ok": True}

@app.get("/auth/me")
async def auth_me(
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    account = await current_account(authorization, session_cookie)
    return {"account": await account_response(account)}

@app.get("/accounts")
async def list_accounts(
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)
    return {"accounts": await memory.list_accounts()}

@app.get("/accounts/audit-logs")
async def list_account_audit_logs(
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)
    return {"logs": await memory.list_account_audit_logs()}

@app.get("/admin/ai-usage/users")
async def list_admin_ai_usage_users(
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)
    quota = QuotaService(memory)
    return {"users": await quota.admin_usage_users()}

@app.get("/accounts/{account_id}/permissions")
async def get_account_permissions(
    account_id: int,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)
    effective = await memory.get_effective_permissions(account_id)
    if not effective:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    return effective

@app.put("/accounts/{account_id}/permissions")
async def update_account_permissions(
    account_id: int,
    payload: AccountPermissionsIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    actor = await require_super_admin(authorization, session_cookie)
    target = await memory.get_account(account_id)
    if not target:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    if target["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Không chỉnh quyền Super Admin gốc")
    effective = await memory.replace_account_permissions(
        account_id=account_id,
        enabled_keys=payload.permissions,
        actor_account_id=actor["id"],
    )
    return effective

@app.post("/accounts")
async def create_account(
    payload: AccountCreateIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    actor = await require_super_admin(authorization, session_cookie)
    username = payload.username.strip()
    display_name = payload.display_name.strip()

    if not username or not display_name:
        raise HTTPException(status_code=400, detail="Username và tên hiển thị không được để trống")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Mật khẩu phải có ít nhất 8 ký tự")
    if payload.role not in {"admin", "member"}:
        raise HTTPException(status_code=400, detail="Chỉ được tạo role admin hoặc member")

    account = await memory.create_account(
        username=username,
        display_name=display_name,
        password=payload.password,
        role=payload.role,
        actor_account_id=actor["id"],
    )
    if not account:
        raise HTTPException(status_code=409, detail="Username đã tồn tại")

    return {"account": account}

@app.patch("/accounts/{account_id}")
async def update_account(
    account_id: int,
    payload: AccountUpdateIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    actor = await require_super_admin(authorization, session_cookie)
    existing = await memory.get_account(account_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")

    if payload.role is not None and payload.role not in {"admin", "member"}:
        raise HTTPException(status_code=400, detail="Role chỉ được là admin hoặc member")
    if payload.status is not None and payload.status not in {"active", "locked"}:
        raise HTTPException(status_code=400, detail="Trạng thái chỉ được là active hoặc locked")
    if existing["role"] == "super_admin" and (payload.role is not None or payload.status is not None):
        raise HTTPException(status_code=400, detail="Không đổi role hoặc khóa Super Admin gốc ở bước này")
    if payload.display_name is not None and not payload.display_name.strip():
        raise HTTPException(status_code=400, detail="Tên hiển thị không được để trống")

    account = await memory.update_account(
        account_id=account_id,
        display_name=payload.display_name,
        role=payload.role,
        status=payload.status,
        actor_account_id=actor["id"],
    )
    return {"account": account}

@app.post("/accounts/{account_id}/reset-password")
async def reset_account_password(
    account_id: int,
    payload: ResetPasswordIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    actor = await require_super_admin(authorization, session_cookie)
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Mật khẩu phải có ít nhất 8 ký tự")

    account = await memory.reset_account_password(
        account_id=account_id,
        new_password=payload.password,
        actor_account_id=actor["id"],
    )
    if not account:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")

    return {"ok": True, "account": account}

@app.delete("/accounts/{account_id}")
async def delete_account(
    account_id: int,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    actor = await require_super_admin(authorization, session_cookie)
    existing = await memory.get_account(account_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    if existing["id"] == actor["id"]:
        raise HTTPException(status_code=400, detail="Không được tự xóa tài khoản đang đăng nhập")
    if existing["role"] == "super_admin":
        raise HTTPException(status_code=400, detail="Không được xóa Super Admin")

    deleted = await memory.delete_account(account_id, actor_account_id=actor["id"])
    return {"ok": True, "account": deleted}

@app.get("/condition-types")
async def list_condition_types(
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)

    return {
        "types": await memory.list_condition_types()
    }


@app.post("/condition-types")
async def create_condition_type(
    payload: ConditionTypeIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)

    if not payload.label.strip():
        raise HTTPException(status_code=400, detail="Tên type không được trống")

    type_id = await memory.create_condition_type(payload.label.strip())

    if not type_id:
        raise HTTPException(status_code=409, detail="Type đã tồn tại")

    return {
        "ok": True,
        "id": type_id
    }

@app.get("/condition-templates")
async def list_condition_templates(
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)
    templates = await memory.list_condition_templates()
    return {
        "templates": [
            resolve_template_support(template)
            for template in templates
        ]
    }


@app.post("/condition-templates")
async def create_condition_template(
    payload: ConditionTemplateIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    actor = await require_super_admin(authorization, session_cookie)

    if not payload.name.strip() or not payload.condition_logic.strip() or not payload.description.strip():
        raise HTTPException(status_code=400, detail="Ten va noi dung mau dieu kien khong duoc trong")

    template_id = await memory.create_condition_template(
        type=payload.type.strip(),
        name=payload.name.strip(),
        condition_logic=payload.condition_logic.strip(),
        description=payload.description.strip(),
        created_by=f'{actor["username"]} ({actor["role"]})',
    )

    return {
        "ok": True,
        "id": template_id,
    }

@app.patch("/condition-templates/{template_id}")
async def update_condition_template(
    template_id: int,
    payload: ConditionTemplateUpdateIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(
        authorization,
        session_cookie
    )

    if not payload.name.strip() or not payload.condition_logic.strip() or not payload.description.strip():
        raise HTTPException(
            status_code=400,
            detail="Ten va noi dung mau dieu kien khong duoc trong"
        )

    await memory.update_condition_template(
        template_id=template_id,
        type=payload.type.strip(),
        name=payload.name.strip(),
            condition_logic=payload.condition_logic.strip(),
        description=payload.description.strip(),
    )

    return {"ok": True}

@app.post("/condition-templates/{template_id}/confirm")
async def confirm_condition_template(
    template_id: int,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(
        authorization,
        session_cookie
    )

    template = await memory.get_condition_template(template_id)

    if not template:
        raise HTTPException(
            status_code=404,
            detail="Khong tim thay mau dieu kien"
        )

    support = resolve_template_support(template)

    if support["support_status"] != "supported":
        raise HTTPException(
            status_code=400,
            detail="Dieu kien nay chua duoc backend ho tro"
        )

    await memory.confirm_condition_template(
        template_id=template_id
    )

    return {"ok": True}

@app.post("/condition-templates/{template_id}/test")
async def test_condition_template(
    template_id: int,
    payload: ConditionTestIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(
        default=None,
        alias=AUTH_COOKIE_NAME
    ),
):
    await require_super_admin(
        authorization,
        session_cookie
    )

    template = await memory.get_condition_template(
        template_id
    )

    if not template:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy mẫu điều kiện"
        )

    context = payload.context or {}

    context["condition_key"] = template_condition_key(template)

    return await run_condition(
        template_id=template_id,
        context=context
    )

@app.post("/condition-test")
async def test_condition_direct(
    payload: DirectConditionTestIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(
        default=None,
        alias=AUTH_COOKIE_NAME
    ),
):
    await require_super_admin(
        authorization,
        session_cookie
    )

    context = {
        "condition_key": payload.condition_key,
    }

    if payload.date:
        context["date"] = payload.date

    if payload.ticker:
        context["ticker"] = payload.ticker

    return await run_condition(
        template_id=0,
        context=context
    )
    
@app.delete("/condition-templates/{template_id}")
async def delete_condition_template(
    template_id: int,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)

    await memory.delete_condition_template(template_id)

    return {"ok": True}

@app.get("/condition-flows")
async def list_condition_flows(
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)

    return {
        "flows": await memory.list_condition_flows()
    }


@app.post("/condition-flows")
async def create_condition_flow(
    payload: ConditionFlowIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    actor = await require_super_admin(authorization, session_cookie)

    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Tên flow không được trống")

    if not payload.expression.strip():
        raise HTTPException(status_code=400, detail="Biểu thức điều kiện không được trống")

    if not payload.prompt_template.strip():
        raise HTTPException(status_code=400, detail="Câu mẫu không được trống")

    if payload.status not in {"draft", "confirmed", "running", "disabled"}:
        raise HTTPException(status_code=400, detail="Trạng thái không hợp lệ")

    refs = await resolve_valid_flow_refs(payload.expression.strip())

    if not refs:
        raise HTTPException(status_code=400, detail="Vui lòng chọn điều kiện đã xác nhận ở bước 1")

    flow_id = await memory.create_condition_flow(
        name=payload.name.strip(),
        expression=flow_refs_expression(refs),
        prompt_template=payload.prompt_template.strip(),
        trigger_prompt=payload.trigger_prompt.strip(),
        created_by=f'{actor["username"]} ({actor["role"]})',
    )

    return {
        "ok": True,
        "id": flow_id,
    }


@app.patch("/condition-flows/{flow_id}")
async def update_condition_flow(
    flow_id: int,
    payload: ConditionFlowUpdateIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)

    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Tên flow không được trống")

    if not payload.expression.strip():
        raise HTTPException(status_code=400, detail="Biểu thức điều kiện không được trống")

    if not payload.prompt_template.strip():
        raise HTTPException(status_code=400, detail="Câu mẫu không được trống")

    if payload.status not in {"draft", "confirmed", "running", "disabled"}:
        raise HTTPException(status_code=400, detail="Trạng thái không hợp lệ")

    refs = await resolve_valid_flow_refs(payload.expression.strip())

    if not refs:
        raise HTTPException(status_code=400, detail="Vui lòng chọn điều kiện đã xác nhận ở bước 1")

    await memory.update_condition_flow(
        flow_id=flow_id,
        name=payload.name.strip(),
        expression=flow_refs_expression(refs),
        prompt_template=payload.prompt_template.strip(),
        trigger_prompt=payload.trigger_prompt.strip(),
        status=payload.status,
    )

    return {"ok": True}


@app.patch("/condition-flows/{flow_id}/trigger-prompt")
async def update_condition_flow_trigger_prompt(
    flow_id: int,
    payload: ConditionFlowTriggerPromptIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)

    flow = await memory.get_condition_flow(flow_id)

    if not flow:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẫu kết hợp")

    await memory.update_condition_flow_trigger_prompt(
        flow_id=flow_id,
        trigger_prompt=payload.trigger_prompt.strip(),
    )

    return {
        "ok": True,
        "id": flow_id,
        "trigger_prompt": payload.trigger_prompt.strip(),
    }

@app.post("/condition-flows/{flow_id}/confirm")
async def confirm_condition_flow(
    flow_id: int,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)

    await memory.confirm_condition_flow(flow_id)

    return {"ok": True}


@app.patch("/condition-flows/{flow_id}/active")
async def set_condition_flow_active(
    flow_id: int,
    payload: ConditionFlowActiveIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)

    flow = await memory.get_condition_flow(flow_id)

    if not flow:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẫu kết hợp")

    if flow["status"] != "confirmed":
        raise HTTPException(status_code=400, detail="Chỉ bật/tắt mẫu đã xác nhận")

    await memory.set_condition_flow_active(flow_id, payload.active)

    return {
        "ok": True,
        "id": flow_id,
        "active": payload.active,
    }


@app.post("/condition-flows/{flow_id}/demo-check")
async def demo_check_condition_flow(
    flow_id: int,
    payload: ConditionFlowDemoCheckIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)

    flow = await memory.get_condition_flow(flow_id)

    if not flow:
        raise HTTPException(status_code=404, detail="Không tìm thấy mẫu kết hợp")

    if flow["status"] != "confirmed":
        raise HTTPException(status_code=400, detail="Mẫu kết hợp chưa được xác nhận")

    context = dict(payload.context or {})
    context.setdefault("date", datetime.now().strftime("%Y-%m-%d"))

    condition_results = []
    matches = {}
    refs = await resolve_valid_flow_refs(flow["expression"])

    for ref in refs:
        template_id = ref["id"]
        template = await memory.get_condition_template(template_id)

        if not template:
            result = {
                "ok": False,
                "matched": False,
                "message": "Không tìm thấy điều kiện",
                "template_id": template_id,
            }
        else:
            condition_context = {
                **context,
                "condition_key": template_condition_key(template),
            }
            result = await run_condition(
                template_id=template_id,
                context=condition_context,
            )
            result["template_id"] = template_id
            result["template_name"] = template.get("name")

        matches[template_id] = bool(result.get("matched"))
        condition_results.append(result)

    matched = evaluate_flow_expression(flow_refs_expression(refs), matches)
    delivered = []
    demo_message = build_demo_flow_ai_message(
        flow["name"],
        condition_results,
        trigger_prompt=flow.get("trigger_prompt"),
        check_date=context.get("date"),
    )

    if matched:
        for user in await memory.list_sales_demo_users():
            await memory.add(user["id"], "assistant", demo_message)
            delivered.append(user["id"])

    return {
        "ok": True,
        "matched": matched,
        "message": demo_message,
        "check_date": context.get("date"),
        "delivered_count": len(delivered),
        "delivered_users": delivered,
        "results": condition_results,
    }


@app.delete("/condition-flows/{flow_id}")
async def delete_condition_flow(
    flow_id: int,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)

    await memory.delete_condition_flow(flow_id)

    return {"ok": True}


@app.get("/case-ideas")
async def list_case_ideas(
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_admin_or_super_admin(authorization, session_cookie)
    return {"cases": await memory.list_case_ideas()}


@app.post("/case-ideas")
async def create_case_idea(
    payload: CaseIdeaIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    account = await require_admin_or_super_admin(authorization, session_cookie)

    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Tên case không được trống")

    case_id = await memory.create_case_idea(
        name=payload.name.strip(),
        indicators=payload.indicators.strip(),
        description=payload.description.strip(),
        created_by=account["username"],
    )

    return {"ok": True, "id": case_id}


@app.patch("/case-ideas/{case_id}")
async def update_case_idea(
    case_id: int,
    payload: CaseIdeaIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_admin_or_super_admin(authorization, session_cookie)

    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Tên case không được trống")

    case = await memory.get_case_idea(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Không tìm thấy case")

    await memory.update_case_idea(
        case_id=case_id,
        name=payload.name.strip(),
        indicators=payload.indicators.strip(),
        description=payload.description.strip(),
    )

    return {"ok": True}


@app.post("/case-ideas/{case_id}/confirm")
async def confirm_case_idea(
    case_id: int,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_admin_or_super_admin(authorization, session_cookie)

    case = await memory.get_case_idea(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Không tìm thấy case")

    await memory.set_case_idea_supported(case_id)

    return {"ok": True}


@app.delete("/case-ideas/{case_id}")
async def delete_case_idea(
    case_id: int,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_admin_or_super_admin(authorization, session_cookie)
    await memory.delete_case_idea(case_id)
    return {"ok": True}


@app.get("/sales-discovery/opening")
def sales_discovery_opening():
    return {"message": OPENING_MESSAGE}


@app.get("/sales-discovery/targets")
async def list_sales_discovery_targets(
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_admin_or_super_admin(authorization, session_cookie)
    return {"targets": await memory.list_sales_discovery_targets()}


@app.post("/sales-discovery/targets")
async def create_sales_discovery_target(
    payload: SalesDiscoveryTargetIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    account = await require_admin_or_super_admin(authorization, session_cookie)

    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Tên target không được trống")

    if payload.status not in {"waiting", "supported", "confirmed", "disabled"}:
        raise HTTPException(status_code=400, detail="Trạng thái target không hợp lệ")

    target_key = payload.target_key.strip() or make_sales_target_key(payload.name)
    recognizer_key = payload.recognizer_key.strip() or target_key

    try:
        target_id = await memory.create_sales_discovery_target(
            target_key=target_key,
            name=payload.name.strip(),
            description=payload.description.strip(),
            suggested_question=payload.suggested_question.strip(),
            recognizer_key=recognizer_key,
            status=payload.status,
            active=payload.active,
            created_by=account["username"],
        )
    except Exception:
        raise HTTPException(status_code=409, detail="Target đã tồn tại hoặc key bị trùng")

    return {"ok": True, "id": target_id}


@app.patch("/sales-discovery/targets/{target_id}")
async def update_sales_discovery_target(
    target_id: int,
    payload: SalesDiscoveryTargetIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_admin_or_super_admin(authorization, session_cookie)

    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Tên target không được trống")

    if payload.status not in {"waiting", "supported", "confirmed", "disabled"}:
        raise HTTPException(status_code=400, detail="Trạng thái target không hợp lệ")

    await memory.update_sales_discovery_target(
        target_id=target_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        suggested_question=payload.suggested_question.strip(),
        recognizer_key=payload.recognizer_key.strip() or payload.target_key.strip(),
        status=payload.status,
        active=payload.active,
    )

    return {"ok": True}


@app.delete("/sales-discovery/targets/{target_id}")
async def delete_sales_discovery_target(
    target_id: int,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_admin_or_super_admin(authorization, session_cookie)
    await memory.delete_sales_discovery_target(target_id)
    return {"ok": True}


@app.post("/sales-discovery/targets/{target_id}/reorder")
async def reorder_sales_discovery_target(
    target_id: int,
    payload: SalesDiscoveryTargetReorderIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_admin_or_super_admin(authorization, session_cookie)

    if payload.direction not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="Hướng sắp xếp không hợp lệ")

    ok = await memory.reorder_sales_discovery_target(target_id, payload.direction)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy target")

    return {"ok": True}


@app.get("/sales-discovery/users")
async def list_sales_discovery_users():
    return {"users": await memory.list_sales_demo_users()}

@app.post("/sales-discovery/users")
async def create_sales_discovery_user():
    user = await memory.create_sales_demo_user()
    return {"user": user}

@app.delete("/sales-discovery/users/{user_id}")
async def delete_sales_discovery_user(user_id: str):
    await memory.delete_user_data(user_id)
    return {"ok": True, "user_id": user_id}

@app.get("/sales-discovery/state/{user_id}")
async def sales_discovery_state(user_id: str):
    assert sales is not None
    return await sales.get_or_create_state(user_id)

@app.get("/sales-discovery/profile/{user_id}")
async def get_sales_discovery_profile(user_id: str):
    return {"profile": await memory.get_customer_profile(user_id)}

@app.post("/sales-discovery/profile/{user_id}")
async def save_sales_discovery_profile(user_id: str, payload: ProfileIn):
    assert sales is not None

    await memory.upsert_customer_profile(
        user_id=user_id,
        gender=payload.gender,
        birth_year=payload.birth_year,
        investment_experience=payload.investment_experience,
    )

    state = await sales.get_or_create_state(user_id)
    targets = state["targets"]
    profile_value = (
        f"Giới tính: {payload.gender}; "
        f"Năm sinh: {payload.birth_year}; "
        f"Thâm niên đầu tư: {payload.investment_experience}"
    )
    targets["investment_experience"]["status"] = "complete"
    targets["investment_experience"]["value"] = profile_value

    await memory.upsert_sales_discovery(
        user_id=user_id,
        stage="collecting",
        targets_json=json.dumps(targets, ensure_ascii=False),
    )

    next_question = await sales.next_collection_question_ai(
        targets,
        state.get("target_configs"),
    )
    message = "Em đã ghi nhận thông tin ban đầu. Mình bắt đầu tư vấn danh mục nhé.\n\n" + next_question
    await memory.add(user_id, "assistant", message)

    return {
        "ok": True,
        "profile": {
            "gender": payload.gender,
            "birth_year": payload.birth_year,
            "investment_experience": payload.investment_experience,
        },
        "state": {
            "stage": "collecting",
            "targets": targets,
            "summary": None,
        },
        "message": message,
    }

@app.get("/chat/history/{user_id}")
async def chat_history(user_id: str):
    return {"messages": await memory.all_messages(user_id)}

@app.get("/frontend/{path:path}")
def serve_static(path: str):
    return FileResponse(os.path.join(FRONTEND_DIR, path))

@app.post("/chat/stream")
async def chat_stream(
    payload: ChatIn,
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    assert orch is not None
    await require_optional_permission(
        authorization,
        session_cookie
    )

    async def gen():
        async for event, data in _agen(payload):
            yield sse(event, data)

    return StreamingResponse(gen(), media_type="text/event-stream")

async def _agen(payload: ChatIn):
    assert orch is not None

    if payload.meta and payload.meta.get("mode") == "sales_discovery":
        assert sales is not None

        state = await sales.get_or_create_state(payload.user_id)
        recent_history = await memory.recent_messages(payload.user_id, turns=6)
        explainer = pending_explainer_target(state)

        if explainer and is_affirmative_reply(payload.message):
            explainer_prompt = " ".join(
                part
                for part in [
                    explainer.get("name") or "Thuyết minh chờ mua",
                    explainer.get("description") or "",
                    explainer.get("suggested_question") or "",
                ]
                if part
            )
            text = await orch._answer_waitbuy_explanation(
                user_text=explainer_prompt,
                model=pick_model(payload.model),
            )
            for i in range(0, len(text), 60):
                chunk = text[i:i + 60]
                if chunk:
                    yield "delta", {"text": chunk}

            targets = state.get("targets") or {}
            key = explainer["target_key"]
            targets[key] = {
                "label": explainer.get("name") or key,
                "status": "complete",
                "value": "Đã thuyết minh cho khách",
            }
            stage = "completed" if sales_state_completed(targets, state.get("target_configs") or []) else "collecting"
            await memory.upsert_sales_discovery(
                user_id=payload.user_id,
                stage=stage,
                targets_json=json.dumps(targets, ensure_ascii=False),
                summary_json=state.get("summary"),
            )
            await memory.add(payload.user_id, "user", payload.message)
            await memory.add(payload.user_id, "assistant", text)

            yield "done", {
                "sources": [],
                "stage": stage,
                "targets": targets,
                "summary": state.get("summary"),
            }
            return

        if explainer and is_negative_reply(payload.message):
            targets = state.get("targets") or {}
            key = explainer["target_key"]
            targets[key] = {
                "label": explainer.get("name") or key,
                "status": "complete",
                "value": "Khách không muốn tìm hiểu lúc này",
            }
            stage = "completed" if sales_state_completed(targets, state.get("target_configs") or []) else "collecting"
            await memory.upsert_sales_discovery(
                user_id=payload.user_id,
                stage=stage,
                targets_json=json.dumps(targets, ensure_ascii=False),
                summary_json=state.get("summary"),
            )
            text = "Dạ, em bỏ qua phần này."
            yield "delta", {"text": text}
            await memory.add(payload.user_id, "user", payload.message)
            await memory.add(payload.user_id, "assistant", text)
            yield "done", {
                "stage": stage,
                "targets": targets,
                "summary": state.get("summary"),
            }
            return

        route = (
            "normal"
            if state["stage"] == "completed"
            else await sales.classify_turn_route(payload.message, state["targets"])
        )
        if route == "normal":
            done_data = {}
            async for event, data in orch.chat_stream(
                user_id=payload.user_id,
                user_text=payload.message,
                language=payload.language,
                selected_model=payload.model,
            ):
                if event == "done":
                    done_data = data
                    continue
                yield event, data

            if state["stage"] != "completed":
                follow_up = await sales.next_collection_question_ai(
                    state["targets"],
                    state.get("target_configs"),
                    user_text=payload.message,
                    history=recent_history,
                )
                if follow_up:
                    text = "\n\n" + follow_up
                    for i in range(0, len(text), 60):
                        chunk = text[i:i + 60]
                        if chunk:
                            yield "delta", {"text": chunk}
                    await memory.add(payload.user_id, "assistant", follow_up)

            yield "done", done_data
            return

        result = await sales.handle_turn(payload.user_id, payload.message)

        text = result["assistant_message"]
        for i in range(0, len(text), 60):
            chunk = text[i:i + 60]
            if chunk:
                yield "delta", {"text": chunk}

        await memory.add(payload.user_id, "user", payload.message)
        await memory.add(payload.user_id, "assistant", text)
        yield "done", {
            "stage": result.get("stage"),
            "targets": result.get("targets"),
            "summary": result.get("summary_for_db"),
        }
        return

    async for event, data in orch.chat_stream(
        user_id=payload.user_id,
        user_text=payload.message,
        language=payload.language,
        selected_model=payload.model,
    ):
        yield event, data

if __name__ == "__main__":
    import uvicorn
    from settings import HOST, PORT
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)

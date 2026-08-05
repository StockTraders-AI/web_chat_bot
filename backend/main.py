import json, os, re, zipfile
from io import BytesIO
from xml.etree import ElementTree
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
    resolve_condition_key,
    is_realtime_wave_condition_key,
    waitbuy_threshold_from_key,
    buy_threshold_from_key,
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
from core.chat_runtime import stream_standard_chat
from core.sales_discovery import OPENING_MESSAGE, SalesDiscovery, is_explainer_target
from core.model_router import pick_model
from core.quota import QuotaService
from core.realtime_wave import add_wave_listener, ensure_realtime_wave_client, start_realtime_wave_client, stop_realtime_wave_client, wave_debug_snapshot, wave_status
from routes.iplatform_api import configure_iplatform_api, router as iplatform_router
from routes.portfolio_chat import configure_portfolio_chat_api, router as portfolio_chat_router
from services.openai_client import OpenAIClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
app = FastAPI(title="StockTraders AI Chat")
app.include_router(iplatform_router)
app.include_router(portfolio_chat_router)

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
    trigger_prompt: Optional[str] = None
    trigger_title: Optional[str] = None
    trigger_recommendation: Optional[str] = None
    trigger_docs: Optional[str] = None
    trigger_docs_file_text: Optional[str] = None
    trigger_docs_file_names: Optional[str] = None


class ConditionFlowActiveIn(BaseModel):
    active: bool


class ConditionFlowTriggerPromptIn(BaseModel):
    trigger_prompt: str = ""
    trigger_title: Optional[str] = None
    trigger_recommendation: Optional[str] = None
    trigger_docs: Optional[str] = None
    trigger_docs_file_text: Optional[str] = None
    trigger_docs_file_names: Optional[str] = None


class ConditionFlowIn(BaseModel):
    name: str
    expression: str
    prompt_template: str
    trigger_prompt: str = ""
    trigger_title: str = ""
    trigger_recommendation: str = ""
    trigger_docs: str = ""
    trigger_docs_file_text: str = ""
    trigger_docs_file_names: str = ""
    status: str = "draft"


class ConditionFlowUpdateIn(BaseModel):
    name: str
    expression: str
    prompt_template: str
    trigger_prompt: str = ""
    trigger_title: str = ""
    trigger_recommendation: str = ""
    trigger_docs: str = ""
    trigger_docs_file_text: str = ""
    trigger_docs_file_names: str = ""
    status: str = "draft"


class CaseIdeaIn(BaseModel):
    name: str
    indicators: str = ""
    description: str = ""
    docs: str = ""
    docs_file_text: str = ""
    docs_file_names: str = ""


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


class DoSongAdviceIn(BaseModel):
    check_date: str = ""
    signal_keys: list[str] = []
    wave: Dict[str, Any] = {}
    engine: Dict[str, Any] = {}
    raw_engine: Dict[str, Any] = {}
    nearest_engine: Dict[str, Any] = {}

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


def combine_trigger_docs(manual_docs: Any = "", file_docs: Any = "") -> str:
    parts = [
        compact_signal_text(manual_docs, "", max_chars=8000),
        compact_signal_text(file_docs, "", max_chars=8000),
    ]
    return "\n\n".join(part for part in parts if part)


def extract_docx_text(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(raw)) as docx:
            xml = docx.read("word/document.xml")
    except Exception:
        raise HTTPException(status_code=400, detail="Khong doc duoc noi dung DOCX")

    try:
        root = ElementTree.fromstring(xml)
    except Exception:
        raise HTTPException(status_code=400, detail="Khong doc duoc noi dung DOCX")

    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def build_demo_flow_ai_message(
    flow_name: str,
    condition_results: list[dict],
    trigger_prompt: str | None,
    check_date: str | None,
    trigger_docs: str | None = None,
) -> str:
    return build_demo_flow_ai_signal(
        flow_name,
        condition_results,
        trigger_prompt=trigger_prompt,
        check_date=check_date,
        trigger_docs=trigger_docs,
    )["response"]


def compact_signal_text(value: Any, fallback: str = "", max_chars: int = 220) -> str:
    text = str(value or fallback or "").strip()
    text = " ".join(text.split())

    if len(text) <= max_chars:
        return text

    return text[:max_chars].rsplit(" ", 1)[0].strip()


SIGNAL_CARD_FILLER_SEGMENTS = (
    "d\u00f2ng ti\u1ec1n c\u1ea3i thi\u1ec7n r\u00f5 h\u01a1n",
    "t\u00edn hi\u1ec7u t\u00edch c\u1ef1c h\u01a1n",
    "c\u1ea7n quan s\u00e1t th\u00eam",
    "th\u1ecb tr\u01b0\u1eddng \u1ed5n \u0111\u1ecbnh h\u01a1n",
    "gi\u1eef k\u1ef7 lu\u1eadt",
    "\u0111\u00e1ng ch\u00fa \u00fd",
    "c\u1ea3i thi\u1ec7n",
    "t\u00edch c\u1ef1c",
    "th\u1eadn tr\u1ecdng",
    "r\u00f5 h\u01a1n",
    "th\u00eam",
    "m\u1ea1nh",
    "h\u01a1n",
    "r\u00f5",
    "\u00fd",
)


def count_visible_signal_chars(value: Any) -> int:
    return sum(1 for char in str(value or "") if not char.isspace())


SIGNAL_DANGLING_WORDS = {
    "va", "voi", "tu", "vao", "de", "khi", "neu", "cho", "cua", "ve", "trong", "theo", "tai",
    "và", "với", "từ", "vào", "để", "khi", "nếu", "cho", "của", "về", "trong", "theo", "tại",
}


def close_signal_sentence(text: str, target_visible_chars: int) -> str:
    text = " ".join(str(text or "").split()).strip(" ,;:")
    words = text.split()
    while words and words[-1].strip(".,!?;:").lower() in SIGNAL_DANGLING_WORDS:
        words.pop()
    text = " ".join(words).strip(" ,;:")
    if not text:
        return ""
    if text[-1] in ".!?":
        return text
    if count_visible_signal_chars(text + ".") <= target_visible_chars:
        return text + "."
    return text


def truncate_to_visible_signal_chars(text: str, target_visible_chars: int) -> str:
    if target_visible_chars <= 0:
        return ""

    source = " ".join(str(text or "").split()).strip()
    if count_visible_signal_chars(source) <= target_visible_chars:
        return close_signal_sentence(source, target_visible_chars)

    visible_count = 0
    output: list[str] = []

    for char in source:
        if not char.isspace():
            if visible_count >= target_visible_chars:
                break
            visible_count += 1
        output.append(char)

    clipped = " ".join("".join(output).split()).strip()
    min_visible = max(24, int(target_visible_chars * 0.45))

    for pattern in (r"[.!?]", r"[,;:]"):
        matches = list(re.finditer(pattern, clipped))
        for match in reversed(matches):
            candidate = clipped[:match.start() if pattern == r"[,;:]" else match.end()].strip()
            if count_visible_signal_chars(candidate) >= min_visible:
                return close_signal_sentence(candidate, target_visible_chars)

    if " " in clipped:
        candidate = clipped.rsplit(" ", 1)[0]
        if count_visible_signal_chars(candidate) >= min_visible:
            return close_signal_sentence(candidate, target_visible_chars)

    return close_signal_sentence(clipped, target_visible_chars)


def build_visible_signal_filler(gap: int) -> str:
    if gap <= 0:
        return ""

    segment_lengths = [
        (segment, count_visible_signal_chars(segment))
        for segment in SIGNAL_CARD_FILLER_SEGMENTS
    ]
    best: dict[int, list[str]] = {0: []}

    for amount in range(1, gap + 1):
        candidate_best: list[str] | None = None
        for segment, length in segment_lengths:
            previous = best.get(amount - length)
            if previous is None:
                continue
            candidate = previous + [segment]
            if candidate_best is None or len(candidate) < len(candidate_best):
                candidate_best = candidate
        if candidate_best is not None:
            best[amount] = candidate_best

    segments = best.get(gap)
    if not segments:
        return "." * gap

    return " " + " ".join(segments)


def fit_signal_text_by_visible_chars(
    value: Any,
    fallback: str = "",
    target_visible_chars: int = 100,
    pad_short: bool = False,
) -> str:
    text = compact_signal_text(value, fallback, max_chars=max(1000, target_visible_chars * 4))

    if count_visible_signal_chars(text) > target_visible_chars:
        return truncate_to_visible_signal_chars(text, target_visible_chars)

    text = text.rstrip(".!?;:, ")
    visible_count = count_visible_signal_chars(text)
    if visible_count >= target_visible_chars or not pad_short:
        return truncate_to_visible_signal_chars(text, target_visible_chars)

    text = compact_signal_text(
        text + build_visible_signal_filler(target_visible_chars - visible_count),
        max_chars=max(1000, target_visible_chars * 4),
    )
    return truncate_to_visible_signal_chars(text, target_visible_chars)


def fallback_signal_card(
    flow_name: str,
    condition_results: list[dict],
    trigger_prompt: str | None,
    check_date: str | None,
) -> dict:
    fallback_message = build_demo_flow_message(
        flow_name,
        condition_results,
        trigger_prompt=None,
        check_date=check_date,
    )
    return {
        "title": fit_signal_text_by_visible_chars(
            flow_name,
            "Tin hieu thi truong",
            target_visible_chars=60,
        ),
        "response": fit_signal_text_by_visible_chars(
            fallback_message,
            target_visible_chars=150,
        ),
        "recommendation": fit_signal_text_by_visible_chars(
            "Khuy\u1ebfn ngh\u1ecb: Theo d\u00f5i th\u00eam, ch\u1ec9 gi\u1ea3i ng\u00e2n th\u0103m d\u00f2 khi t\u00edn hi\u1ec7u x\u00e1c nh\u1eadn.",
            target_visible_chars=70,
        ),
    }


def parse_signal_card_ai_content(content: str, fallback: dict) -> dict:
    raw = (content or "").strip()

    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()

    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {}

    if not isinstance(parsed, dict):
        parsed = {}

    return {
        "title": fit_signal_text_by_visible_chars(
            parsed.get("title"),
            fallback["title"],
            target_visible_chars=60,
        ),
        "response": fit_signal_text_by_visible_chars(
            parsed.get("response"),
            fallback["response"],
            target_visible_chars=150,
            pad_short=False,
        ),
        "recommendation": fit_signal_text_by_visible_chars(
            parsed.get("recommendation"),
            fallback["recommendation"],
            target_visible_chars=70,
        ),
    }


def signal_card_length_too_short(card: dict | None) -> bool:
    if not card:
        return True

    title = card.get("title") or ""
    response = card.get("response") or card.get("message") or ""
    recommendation = card.get("recommendation") or ""

    return (
        count_visible_signal_chars(title) < 20
        or count_visible_signal_chars(response) < 90
        or count_visible_signal_chars(recommendation) < 35
    )


def condition_results_wave_metric(condition_results: list[dict]) -> tuple[str, float | None]:
    for result in condition_results or []:
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            continue
        buy = parse_public_float(data.get("buy") or data.get("mua") or data.get("mu"))
        if buy is not None:
            return "buy", buy
        waitbuy = parse_public_float(
            data.get("waitbuy")
            or data.get("waitBuy")
            or data.get("wait_buy")
            or data.get("cho_mua")
            or data.get("cm")
        )
        if waitbuy is not None:
            return "waitbuy", waitbuy
    return "waitbuy", None


def repair_short_signal_card(card: dict, flow_name: str, condition_results: list[dict]) -> dict:
    metric, metric_value = condition_results_wave_metric(condition_results)
    metric_text = f"{metric_value:g}" if metric_value is not None else "cao"
    metric_label = "Mua" if metric == "buy" else "Ch\u1edd mua"

    title = card.get("title") or ""
    response = card.get("response") or card.get("message") or ""
    recommendation = card.get("recommendation") or ""

    if count_visible_signal_chars(title) < 20:
        title = flow_name or f"T\u00edn hi\u1ec7u {metric_label} t\u0103ng cao \u0111\u00e1ng ch\u00fa \u00fd"
    if count_visible_signal_chars(title) < 20:
        title = f"T\u00edn hi\u1ec7u {metric_label} t\u0103ng cao \u0111\u00e1ng ch\u00fa \u00fd"

    if count_visible_signal_chars(response) < 90:
        response = (
            f"{metric_label} hi\u1ec7n \u1edf m\u1ee9c {metric_text}, cho th\u1ea5y l\u1ef1c c\u1ea7u c\u1ea3i thi\u1ec7n v\u00e0 d\u00f2ng ti\u1ec1n b\u1eaft \u0111\u1ea7u quay l\u1ea1i. "
            "T\u00edn hi\u1ec7u n\u00e0y nghi\u00eang v\u1ec1 tr\u1ea1ng th\u00e1i t\u00edch c\u1ef1c h\u01a1n, nh\u01b0ng v\u1eabn c\u1ea7n th\u00eam x\u00e1c nh\u1eadn t\u1eeb di\u1ec5n bi\u1ebfn th\u1ecb tr\u01b0\u1eddng."
        )

    if count_visible_signal_chars(recommendation) < 35:
        recommendation = "Xem x\u00e9t gi\u1ea3i ng\u00e2n th\u0103m d\u00f2, \u0111\u1ed3ng th\u1eddi ch\u1edd t\u00edn hi\u1ec7u x\u00e1c nh\u1eadn r\u00f5 h\u01a1n."

    return {
        "title": fit_signal_text_by_visible_chars(title, target_visible_chars=60),
        "response": fit_signal_text_by_visible_chars(response, target_visible_chars=150),
        "recommendation": fit_signal_text_by_visible_chars(recommendation, target_visible_chars=70),
    }


def build_signal_card_length_instruction(strict: bool = False) -> str:
    prefix = "The previous output was too short. " if strict else ""
    return (
        prefix
        + "Return only one valid JSON object, no markdown, with exactly 3 string fields: "
        "title, response, recommendation. "
        "Follow the admin prompt from UI for tone, wording, and exclusions. "
        "Length is counted excluding whitespace. Target title 20-60 characters, response 90-150 characters, recommendation 35-70 characters. "
        "Do not produce telegraphic one-clause text. Each field must read as a complete sentence or complete phrase, never a dangling fragment. Historical-date output must be as complete as current-date output. "
        "Count every Vietnamese letter, number, and punctuation mark; ignore spaces only. "
        "Do not copy phrases from the UI prompts just to fill length; treat them as guidance for meaning, tone, and exclusions. "
        "If the data contains a current waitbuy or buy value, the response must mention that current value and must not mention the threshold when the admin prompt excludes it. "
        "Terminology rule: waitbuy/Cho mua/Ch? mua is a signal level, not a number of tickers; write Cho mua/Ch? mua ??t m?c X or ? m?c X, never X m? or X c? phi?u for waitbuy."
    )


def build_demo_flow_ai_signal(
    flow_name: str,
    condition_results: list[dict],
    trigger_prompt: str | None,
    check_date: str | None,
    trigger_title: str | None = None,
    trigger_recommendation: str | None = None,
    trigger_docs: str | None = None,
) -> dict:
    fallback = fallback_signal_card(
        flow_name,
        condition_results,
        trigger_prompt=trigger_prompt,
        check_date=check_date,
    )
    title_prompt = (trigger_title or "").strip()
    response_prompt = (trigger_prompt or "").strip()
    recommendation_prompt = (trigger_recommendation or "").strip()
    docs_prompt = compact_signal_text(trigger_docs, "", max_chars=8000)

    if not any([title_prompt, response_prompt, recommendation_prompt, docs_prompt]):
        return fallback

    field_prompt = "\n".join([
        "Generate a 3-field signal card from these UI prompts.",
        f"Title prompt: {title_prompt or 'Create a concise Vietnamese market signal title.'}",
        f"Response prompt: {response_prompt or 'Create a concise Vietnamese market interpretation.'}",
        f"Recommendation prompt: {recommendation_prompt or 'Create a concise Vietnamese action recommendation.'}",
        f"StockTradersAI reference docs: {docs_prompt}" if docs_prompt else "StockTradersAI reference docs: none",
    ])

    try:
        client = OpenAIClient()
        messages = build_demo_flow_ai_messages(
            flow_name=flow_name,
            condition_results=condition_results,
            trigger_prompt=field_prompt,
            check_date=check_date,
        )
        messages.append({
            "role": "user",
            "content": build_signal_card_length_instruction(strict=False),
        })
        resp = client.chat(
            model=DEFAULT_MODEL,
            messages=messages,
            tools=None,
            tool_choice="auto",
        )
        content = (resp.choices[0].message.content or "").strip()
        signal_card = parse_signal_card_ai_content(content, fallback)

        if signal_card_length_too_short(signal_card):
            retry_messages = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": build_signal_card_length_instruction(strict=True)},
            ]
            retry_resp = client.chat(
                model=DEFAULT_MODEL,
                messages=retry_messages,
                tools=None,
                tool_choice="auto",
            )
            retry_content = (retry_resp.choices[0].message.content or "").strip()
            retry_card = parse_signal_card_ai_content(retry_content, fallback)
            if not signal_card_length_too_short(retry_card):
                return retry_card
            return repair_short_signal_card(retry_card, flow_name, condition_results)

        return signal_card
    except Exception as exc:
        print("DEMO_FLOW_AI_MESSAGE_ERROR:", exc)
        return fallback


def parse_signal_response_ai_content(content: str, fallback_response: str) -> str:
    raw = (content or "").strip()

    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()

    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None

    if isinstance(parsed, dict):
        value = (
            parsed.get("response")
            or parsed.get("message")
            or parsed.get("content")
            or raw
        )
    else:
        value = raw

    return fit_signal_text_by_visible_chars(
        value,
        fallback_response,
        target_visible_chars=150,
        pad_short=False,
    )


def build_demo_flow_ai_response(
    flow_name: str,
    condition_results: list[dict],
    trigger_prompt: str | None,
    check_date: str | None,
    trigger_docs: str | None = None,
) -> str:
    fallback = fallback_signal_card(
        flow_name,
        condition_results,
        trigger_prompt=trigger_prompt,
        check_date=check_date,
    )["response"]
    response_prompt = (trigger_prompt or "").strip()
    docs_prompt = compact_signal_text(trigger_docs, "", max_chars=8000)

    if docs_prompt:
        response_prompt = "\n".join([
            response_prompt or "Vi\u1ebft nh\u1eadn \u0111\u1ecbnh th\u1ecb tr\u01b0\u1eddng ng\u1eafn g\u1ecdn b\u1eb1ng ti\u1ebfng Vi\u1ec7t t\u1eeb d\u1eef li\u1ec7u \u0111i\u1ec1u ki\u1ec7n \u0111\u00e3 kh\u1edbp.",
            "T\u00e0i li\u1ec7u tham chi\u1ebfu StockTradersAI:",
            docs_prompt,
        ])

    if not response_prompt:
        response_prompt = "Vi\u1ebft nh\u1eadn \u0111\u1ecbnh th\u1ecb tr\u01b0\u1eddng ng\u1eafn g\u1ecdn b\u1eb1ng ti\u1ebfng Vi\u1ec7t t\u1eeb d\u1eef li\u1ec7u \u0111i\u1ec1u ki\u1ec7n \u0111\u00e3 kh\u1edbp."

    try:
        client = OpenAIClient()
        messages = build_demo_flow_ai_messages(
            flow_name=flow_name,
            condition_results=condition_results,
            trigger_prompt=response_prompt,
            check_date=check_date,
        )
        messages.append({
            "role": "user",
            "content": (
                "Ch\u1ec9 tr\u1ea3 v\u1ec1 m\u1ed9t object JSON h\u1ee3p l\u1ec7, kh\u00f4ng markdown, \u0111\u00fang m\u1ed9t field string: "
                "response. N\u1ed9i dung ph\u1ea3i l\u00e0 ti\u1ebfng Vi\u1ec7t, b\u00e1m theo h\u01b0\u1edbng d\u1eabn nh\u1eadn \u0111\u1ecbnh tr\u00ean giao di\u1ec7n. "
                "Gi\u1edbi h\u1ea1n \u0111\u1ed9 d\u00e0i kh\u00f4ng t\u00ednh kho\u1ea3ng tr\u1eafng: nh\u1eadn \u0111\u1ecbnh t\u1ed1i \u0111a 150 k\u00fd t\u1ef1. "
                "T?nh m?i ch? c?i ti?ng Vi?t, ch? s? v? d?u c?u; ch? b? qua kho?ng tr?ng. "
                "N?u d? li?u c? gi? tr? Ch? mua ho?c Mua hi?n t?i th? ph?i nh?c ??ng gi? tr? hi?n t?i ??. "
                "Kh?ng nh?c ng??ng ?i?u ki?n khi h??ng d?n tr?n giao di?n y?u c?u lo?i tr?."
            ),
        })
        resp = client.chat(
            model=DEFAULT_MODEL,
            messages=messages,
            tools=None,
            tool_choice="auto",
        )
        content = (resp.choices[0].message.content or "").strip()
        return parse_signal_response_ai_content(content, fallback)
    except Exception as exc:
        print("DEMO_FLOW_AI_RESPONSE_ERROR:", exc)
        return fallback

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


def is_active_condition_flow(flow: dict) -> bool:
    return flow.get("status") == "confirmed" and bool(flow.get("active"))


def flow_delivery_key(flow_id: int, check_date: str, condition_results: list[dict]) -> str:
    return f"{flow_id}:{check_date}"


def signal_key_from_condition_keys(condition_keys: list[str]) -> str:
    return "+".join(condition_keys)


def normalize_public_signal_key(signal_key: str | None) -> str | None:
    if not signal_key:
        return signal_key
    if waitbuy_threshold_from_key(signal_key) is not None:
        return "waitbuy_over_threshold"
    if buy_threshold_from_key(signal_key) is not None:
        return "buy_over_threshold"
    return signal_key

def signal_title(flow: dict, condition_results: list[dict]) -> str:
    return (
        flow.get("name")
        or next(
            (result.get("template_name") for result in condition_results if result.get("template_name")),
            "Tin hieu dieu kien",
        )
    )


async def persist_condition_signal(
    flow: dict,
    condition_keys: list[str],
    condition_results: list[dict],
    message: str,
    check_date: str,
    delivery_key: str,
    source: str,
    title: str | None = None,
    recommendation: str = "",
):
    await memory.upsert_condition_signal(
        flow_id=int(flow["id"]),
        flow_name=flow.get("name") or "",
        condition_keys=condition_keys,
        signal_key=signal_key_from_condition_keys(condition_keys),
        title=title or signal_title(flow, condition_results),
        message=message,
        condition_results=condition_results,
        check_date=check_date,
        source=source,
        delivery_key=delivery_key,
        recommendation=recommendation,
    )


def parse_public_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except Exception:
        return None


def signal_wave_metric(signal_key: str | None) -> str | None:
    normalized = normalize_public_signal_key(signal_key)
    if normalized == "waitbuy_over_threshold":
        return "waitbuy"
    if normalized == "buy_over_threshold":
        return "buy"
    return None


def wave_metric_value_from_data(data: dict, metric: str) -> float | None:
    if metric == "buy":
        return parse_public_float(data.get("buy") or data.get("mua") or data.get("mu"))
    return parse_public_float(
        data.get("waitbuy")
        or data.get("waitBuy")
        or data.get("wait_buy")
        or data.get("cho_mua")
        or data.get("cm")
    )


def cached_signal_wave_metric_matches(signal: dict | None, metric: str | None, value: float | None) -> bool:
    if not signal or not metric or value is None:
        return False

    for result in signal.get("condition_results") or []:
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            continue
        cached_value = wave_metric_value_from_data(data, metric)
        if cached_value is not None:
            return abs(cached_value - value) < 0.000001

    return False


async def build_public_historical_wave_signal(
    requested_signal_key: str | None,
    requested_flow_id: int | None,
    check_date: str,
    metric_value: float | None,
) -> dict | None:
    if not check_date or metric_value is None:
        return None

    normalized_signal_key = normalize_public_signal_key(requested_signal_key) or "waitbuy_over_threshold"
    metric = signal_wave_metric(normalized_signal_key)
    if not metric:
        return None

    flows = await memory.list_condition_flows()
    templates = await memory.list_condition_templates()
    templates_by_id = {
        int(template["id"]): template
        for template in templates
        if str(template.get("id", "")).isdigit()
    }

    for flow in flows:
        if requested_flow_id is not None and int(flow.get("id") or 0) != int(requested_flow_id):
            continue
        if not is_active_condition_flow(flow):
            continue

        refs = resolve_flow_condition_refs(flow.get("expression") or "", templates)
        if not refs:
            continue

        condition_keys: list[str] = []
        condition_results: list[dict] = []
        matches: dict[int, bool] = {}

        for ref in refs:
            template_id = int(ref["id"])
            template = templates_by_id.get(template_id)
            if not template:
                result = {
                    "ok": False,
                    "matched": False,
                    "message": "Khong tim thay dieu kien",
                    "template_id": template_id,
                }
            else:
                condition_key = template_condition_key(template)
                resolved_key = resolve_condition_key(condition_key)
                if resolved_key:
                    condition_keys.append(resolved_key)
                result = await run_condition(
                    template_id=template_id,
                    context={
                        "date": check_date,
                        "condition_key": condition_key,
                        metric: metric_value,
                        "source": "stocktraders_web_history",
                    },
                )
                result["template_id"] = template_id
                result["template_name"] = template.get("name")

            matches[template_id] = bool(result.get("matched"))
            condition_results.append(result)

        current_signal_key = signal_key_from_condition_keys(condition_keys)
        if current_signal_key != normalized_signal_key:
            continue

        matched = evaluate_flow_expression(flow_refs_expression(refs), matches)
        if not matched:
            return None

        signal_card = build_demo_flow_ai_signal(
            flow.get("name") or "",
            condition_results,
            trigger_prompt=flow.get("trigger_prompt"),
            check_date=check_date,
            trigger_title=flow.get("trigger_title"),
            trigger_recommendation=flow.get("trigger_recommendation"),
            trigger_docs=combine_trigger_docs(flow.get("trigger_docs"), flow.get("trigger_docs_file_text")),
        )
        delivery_key = f"history:{flow['id']}:{current_signal_key}:{check_date}"
        await persist_condition_signal(
            flow=flow,
            condition_keys=condition_keys,
            condition_results=condition_results,
            message=signal_card["response"],
            check_date=check_date,
            delivery_key=delivery_key,
            source="stocktraders_web_history",
            title=signal_card["title"],
            recommendation=signal_card["recommendation"],
        )
        return await memory.get_latest_condition_signal(
            signal_key=current_signal_key,
            flow_id=int(flow["id"]),
            check_date=check_date,
        )

    return None


async def inspect_realtime_wave_flow(
    flow: dict,
    templates: list[dict] | None = None,
    evaluate_current: bool = True,
    ensure_wave: bool = False,
):
    if ensure_wave:
        await ensure_realtime_wave_client()
    templates = templates if templates is not None else await memory.list_condition_templates()
    templates_by_id = {
        int(template["id"]): template
        for template in templates
        if str(template.get("id", "")).isdigit()
    }
    status = wave_status()
    check_date = status.get("latest_date") or datetime.now().strftime("%Y-%m-%d")
    active_confirmed = is_active_condition_flow(flow)
    refs = resolve_flow_condition_refs(flow.get("expression") or "", templates)
    ref_templates = [templates_by_id.get(int(ref["id"])) for ref in refs]
    resolved_keys = [
        resolve_condition_key(template_condition_key(template))
        for template in ref_templates
        if template
    ]
    signal_key = signal_key_from_condition_keys(resolved_keys)
    realtime_supported = bool(resolved_keys) and all(
        is_realtime_wave_condition_key(key) for key in resolved_keys
    )
    skip_reasons = []

    if flow.get("status") != "confirmed":
        skip_reasons.append("flow_not_confirmed")
    if not bool(flow.get("active")):
        skip_reasons.append("flow_not_active")
    if not refs:
        skip_reasons.append("no_condition_refs")
    if any(template is None for template in ref_templates):
        skip_reasons.append("missing_condition_template")
    if resolved_keys and not realtime_supported:
        skip_reasons.append("has_non_wave_condition")
    if not status.get("connected"):
        skip_reasons.append("wave_socket_not_connected")
    if not status.get("row_count"):
        skip_reasons.append("no_wave_cache")

    condition_results = []
    matches = {}
    matched = None

    state = await memory.get_condition_signal_state(
        int(flow["id"]),
        signal_key,
    ) if signal_key else None
    latest_signal = await memory.get_latest_condition_signal(
        signal_key=signal_key,
        flow_id=int(flow["id"]),
    ) if signal_key else None

    if evaluate_current and active_confirmed and realtime_supported:
        for ref, template in zip(refs, ref_templates):
            template_id = int(ref["id"])
            result = await run_condition(
                template_id=template_id,
                context={
                    "date": check_date,
                    "condition_key": template_condition_key(template),
                },
            )
            result["template_id"] = template_id
            result["template_name"] = template.get("name")
            matches[template_id] = bool(result.get("matched"))
            condition_results.append(result)

        matched = evaluate_flow_expression(flow_refs_expression(refs), matches)

    return {
        "id": flow.get("id"),
        "name": flow.get("name"),
        "status": flow.get("status"),
        "active": bool(flow.get("active")),
        "expression": flow.get("expression"),
        "refs": refs,
        "condition_keys": resolved_keys,
        "signal_key": signal_key,
        "realtime_supported": realtime_supported,
        "active_confirmed": active_confirmed,
        "skip_reasons": skip_reasons,
        "wave": status,
        "check_date": check_date,
        "current_matched": matched,
        "state": state,
        "latest_signal_id": latest_signal.get("id") if latest_signal else None,
        "latest_response": latest_signal.get("message") if latest_signal else None,
        "condition_results": condition_results,
    }


async def handle_realtime_wave_update(payload: dict):
    if not memory:
        return

    templates = await memory.list_condition_templates()
    templates_by_id = {
        int(template["id"]): template
        for template in templates
        if str(template.get("id", "")).isdigit()
    }
    flows = await memory.list_condition_flows()
    status = wave_status()
    check_date = status.get("latest_date") or datetime.now().strftime("%Y-%m-%d")

    for flow in flows:
        if not is_active_condition_flow(flow):
            continue

        refs = resolve_flow_condition_refs(flow.get("expression") or "", templates)
        if not refs:
            continue

        ref_templates = [templates_by_id.get(int(ref["id"])) for ref in refs]
        if any(template is None for template in ref_templates):
            continue

        resolved_keys = [
            resolve_condition_key(template_condition_key(template))
            for template in ref_templates
            if template
        ]

        if not resolved_keys or any(
            not is_realtime_wave_condition_key(key) for key in resolved_keys
        ):
            continue

        condition_results = []
        matches = {}

        for ref, template in zip(refs, ref_templates):
            template_id = int(ref["id"])
            condition_context = {
                "date": check_date,
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
        signal_key = signal_key_from_condition_keys(resolved_keys)
        state = await memory.update_condition_signal_state(
            flow_id=int(flow["id"]),
            signal_key=signal_key,
            matched=matched,
            check_date=check_date,
        )

        if not matched:
            continue

        latest_signal = None
        if not state.get("should_publish"):
            latest_signal = await memory.get_latest_condition_signal(
                signal_key=signal_key,
                flow_id=int(flow["id"]),
            )

        delivery_key = (
            state.get("delivery_key")
            or f"{int(flow['id'])}:{signal_key}:{check_date or 'unknown'}:latest"
        )

        if latest_signal:
            signal_card = {
                "title": latest_signal.get("title") or signal_title(flow, condition_results),
                "response": build_demo_flow_ai_response(
                    flow["name"],
                    condition_results,
                    trigger_prompt=flow.get("trigger_prompt"),
                    check_date=check_date,
                    trigger_docs=combine_trigger_docs(flow.get("trigger_docs"), flow.get("trigger_docs_file_text")),
                ),
                "recommendation": latest_signal.get("recommendation") or "",
            }
        else:
            signal_card = build_demo_flow_ai_signal(
                flow["name"],
                condition_results,
                trigger_prompt=flow.get("trigger_prompt"),
                check_date=check_date,
                trigger_title=flow.get("trigger_title"),
                trigger_recommendation=flow.get("trigger_recommendation"),
                trigger_docs=combine_trigger_docs(flow.get("trigger_docs"), flow.get("trigger_docs_file_text")),
            )
        await persist_condition_signal(
            flow=flow,
            condition_keys=resolved_keys,
            condition_results=condition_results,
            message=signal_card["response"],
            check_date=check_date,
            delivery_key=delivery_key,
            source="realtime_wave",
            title=signal_card["title"],
            recommendation=signal_card["recommendation"],
        )

        for user in await memory.list_sales_demo_users():
            await memory.add(user["id"], "assistant", signal_card["response"])



@app.on_event("startup")
async def startup():
    global orch, sales
    ensure_dirs()
    await memory.init()
    registry.load()
    rag.load()
    orch = Orchestrator(memory=memory, rag=rag, registry=registry)
    configure_iplatform_api(lambda: orch)
    configure_portfolio_chat_api(lambda: orch)
    sales = SalesDiscovery(memory=memory)
    add_wave_listener(handle_realtime_wave_update)
    start_realtime_wave_client()


@app.on_event("shutdown")
async def shutdown():
    await stop_realtime_wave_client()

@app.get("/meta/models")
def meta_models():
    return {"models": ALLOWED_MODELS}

@app.get("/")
def serve_index():
    return FileResponse(
        os.path.join(FRONTEND_DIR, "index.html"),
        headers={"Cache-Control": "no-store"},
    )

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
        trigger_title=payload.trigger_title.strip(),
        trigger_recommendation=payload.trigger_recommendation.strip(),
        trigger_docs=payload.trigger_docs.strip(),
        trigger_docs_file_text=payload.trigger_docs_file_text.strip(),
        trigger_docs_file_names=payload.trigger_docs_file_names.strip(),
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
        trigger_title=payload.trigger_title.strip(),
        trigger_recommendation=payload.trigger_recommendation.strip(),
        trigger_docs=payload.trigger_docs.strip(),
        trigger_docs_file_text=payload.trigger_docs_file_text.strip(),
        trigger_docs_file_names=payload.trigger_docs_file_names.strip(),
        status=payload.status,
    )

    return {"ok": True}



@app.post("/condition-docs/extract")
async def extract_condition_docs_file(
    request: Request,
    filename: str = "",
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_admin_or_super_admin(authorization, session_cookie)

    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="T\u00e0i li\u1ec7u r\u1ed7ng")

    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="T\u00e0i li\u1ec7u t\u1ed1i \u0111a 8MB")

    name = (filename or "").lower()
    content_type = (request.headers.get("content-type") or "").lower()

    if name.endswith(".pdf") or "application/pdf" in content_type:
        try:
            from pypdf import PdfReader
        except Exception:
            raise HTTPException(status_code=500, detail="M\u00e1y ch\u1ee7 ch\u01b0a c\u00e0i pypdf \u0111\u1ec3 \u0111\u1ecdc PDF")

        try:
            reader = PdfReader(BytesIO(raw))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            raise HTTPException(status_code=400, detail="Khong doc duoc noi dung PDF")
    elif name.endswith(".docx") or "officedocument.wordprocessingml.document" in content_type:
        text = extract_docx_text(raw)
    else:
        text = raw.decode("utf-8", errors="ignore")

    text = compact_signal_text(text, "", max_chars=8000)
    if not text:
        raise HTTPException(status_code=400, detail="Khong trich duoc noi dung file")

    return {"ok": True, "text": text}

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

    trigger_title = payload.trigger_title.strip() if payload.trigger_title is not None else None
    trigger_recommendation = (
        payload.trigger_recommendation.strip()
        if payload.trigger_recommendation is not None
        else None
    )
    trigger_docs = payload.trigger_docs.strip() if payload.trigger_docs is not None else None
    trigger_docs_file_text = (
        payload.trigger_docs_file_text.strip()
        if payload.trigger_docs_file_text is not None
        else None
    )
    trigger_docs_file_names = (
        payload.trigger_docs_file_names.strip()
        if payload.trigger_docs_file_names is not None
        else None
    )

    await memory.update_condition_flow_trigger_prompt(
        flow_id=flow_id,
        trigger_prompt=payload.trigger_prompt.strip(),
        trigger_title=trigger_title,
        trigger_recommendation=trigger_recommendation,
        trigger_docs=trigger_docs,
        trigger_docs_file_text=trigger_docs_file_text,
        trigger_docs_file_names=trigger_docs_file_names,
    )

    return {
        "ok": True,
        "id": flow_id,
        "trigger_prompt": payload.trigger_prompt.strip(),
        "trigger_title": trigger_title if trigger_title is not None else flow.get("trigger_title", ""),
        "trigger_recommendation": trigger_recommendation if trigger_recommendation is not None else flow.get("trigger_recommendation", ""),
        "trigger_docs": trigger_docs if trigger_docs is not None else flow.get("trigger_docs", ""),
        "trigger_docs_file_text": trigger_docs_file_text if trigger_docs_file_text is not None else flow.get("trigger_docs_file_text", ""),
        "trigger_docs_file_names": trigger_docs_file_names if trigger_docs_file_names is not None else flow.get("trigger_docs_file_names", ""),
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

    updated_flow = {
        **flow,
        "active": 1 if payload.active else 0,
    }
    realtime_watch = await inspect_realtime_wave_flow(updated_flow, ensure_wave=True)

    return {
        "ok": True,
        "id": flow_id,
        "active": payload.active,
        "realtime_watch": realtime_watch,
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

    if (
        payload.trigger_prompt is not None
        or payload.trigger_title is not None
        or payload.trigger_recommendation is not None
        or payload.trigger_docs is not None
        or payload.trigger_docs_file_text is not None
        or payload.trigger_docs_file_names is not None
    ):
        trigger_prompt = (
            payload.trigger_prompt.strip()
            if payload.trigger_prompt is not None
            else flow.get("trigger_prompt", "")
        )
        trigger_title = (
            payload.trigger_title.strip()
            if payload.trigger_title is not None
            else flow.get("trigger_title", "")
        )
        trigger_recommendation = (
            payload.trigger_recommendation.strip()
            if payload.trigger_recommendation is not None
            else flow.get("trigger_recommendation", "")
        )
        trigger_docs = (
            payload.trigger_docs.strip()
            if payload.trigger_docs is not None
            else flow.get("trigger_docs", "")
        )
        trigger_docs_file_text = (
            payload.trigger_docs_file_text.strip()
            if payload.trigger_docs_file_text is not None
            else flow.get("trigger_docs_file_text", "")
        )
        trigger_docs_file_names = (
            payload.trigger_docs_file_names.strip()
            if payload.trigger_docs_file_names is not None
            else flow.get("trigger_docs_file_names", "")
        )
        await memory.update_condition_flow_trigger_prompt(
            flow_id=flow_id,
            trigger_prompt=trigger_prompt,
            trigger_title=trigger_title,
            trigger_recommendation=trigger_recommendation,
            trigger_docs=trigger_docs,
            trigger_docs_file_text=trigger_docs_file_text,
            trigger_docs_file_names=trigger_docs_file_names,
        )
        flow = {
            **flow,
            "trigger_prompt": trigger_prompt,
            "trigger_title": trigger_title,
            "trigger_recommendation": trigger_recommendation,
            "trigger_docs": trigger_docs,
            "trigger_docs_file_text": trigger_docs_file_text,
            "trigger_docs_file_names": trigger_docs_file_names,
        }

    context = dict(payload.context or {})
    context.setdefault("date", datetime.now().strftime("%Y-%m-%d"))

    condition_results = []
    condition_keys = []
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
            condition_key = template_condition_key(template)
            resolved_key = resolve_condition_key(condition_key)
            if resolved_key:
                condition_keys.append(resolved_key)
            condition_context = {
                **context,
                "condition_key": condition_key,
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
    signal_card = None
    demo_message = None

    if matched:
        signal_card = build_demo_flow_ai_signal(
            flow["name"],
            condition_results,
            trigger_prompt=flow.get("trigger_prompt"),
            check_date=context.get("date"),
            trigger_title=flow.get("trigger_title"),
            trigger_recommendation=flow.get("trigger_recommendation"),
            trigger_docs=combine_trigger_docs(flow.get("trigger_docs"), flow.get("trigger_docs_file_text")),
        )
        demo_message = signal_card["response"]
        if condition_keys:
            signal_key = signal_key_from_condition_keys(condition_keys)
            await persist_condition_signal(
                flow=flow,
                condition_keys=condition_keys,
                condition_results=condition_results,
                message=demo_message,
                check_date=context.get("date"),
                delivery_key=f"demo:{flow_id}:{signal_key}:{context.get('date')}",
                source="demo_check",
                title=signal_card["title"],
                recommendation=signal_card["recommendation"],
            )
        for user in await memory.list_sales_demo_users():
            await memory.add(user["id"], "assistant", demo_message)
            delivered.append(user["id"])

    return {
        "ok": True,
        "matched": matched,
        "message": demo_message,
        "title": signal_card["title"] if signal_card else None,
        "response": signal_card["response"] if signal_card else None,
        "recommendation": signal_card["recommendation"] if signal_card else None,
        "check_date": context.get("date"),
        "delivered_count": len(delivered),
        "delivered_users": delivered,
        "results": condition_results,
    }


@app.get("/condition-realtime/wave/status")
async def condition_realtime_wave_status(
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
    debug: bool = False,
    date: Optional[str] = None,
):
    await require_super_admin(authorization, session_cookie)
    status = await ensure_realtime_wave_client()
    if debug:
        return wave_debug_snapshot(date)
    return status

@app.post("/condition-realtime/wave/restart")
async def condition_realtime_wave_restart(
    authorization: Optional[str] = Header(default=None),
    session_cookie: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
):
    await require_super_admin(authorization, session_cookie)
    before = wave_status()
    await stop_realtime_wave_client()
    after = await ensure_realtime_wave_client()
    return {
        "ok": True,
        "before": before,
        "after": after,
    }


def do_song_advice_fallback(payload: DoSongAdviceIn) -> dict:
    engine = do_song_effective_prompt_engine(payload)
    return {
        "title": fit_signal_text_by_visible_chars(
            engine.get("tieuDe"),
            "Nh\u1eadn \u0111\u1ecbnh th\u1ecb tr\u01b0\u1eddng",
            target_visible_chars=60,
        ),
        "response": fit_signal_text_by_visible_chars(
            engine.get("dienGiai"),
            "D\u00f2ng ti\u1ec1n th\u1ecb tr\u01b0\u1eddng c\u1ea7n th\u00eam t\u00edn hi\u1ec7u x\u00e1c nh\u1eadn tr\u01b0\u1edbc khi k\u1ebft lu\u1eadn tr\u1ea1ng th\u00e1i m\u1edbi.",
            target_visible_chars=150,
        ),
        "recommendation": fit_signal_text_by_visible_chars(
            engine.get("hanhDong"),
            "Gi\u1eef k\u1ef7 lu\u1eadt danh m\u1ee5c v\u00e0 ch\u1edd t\u00edn hi\u1ec7u r\u00f5 r\u00e0ng h\u01a1n.",
            target_visible_chars=70,
        ),
    }


def unique_signal_keys(keys: list[str | None]) -> list[str]:
    output = []
    for key in keys:
        normalized = normalize_public_signal_key(key)
        if normalized and normalized not in output:
            output.append(normalized)
    return output


DISABLED_DOSONG_STATES = {"s2", "s3"}


def disabled_do_song_signal_key(key: str, payload: DoSongAdviceIn) -> bool:
    state = str((payload.engine or {}).get("maTrangThai") or "").strip().lower()
    normalized = normalize_public_signal_key(key) or str(key or "").strip()
    if state in {"s2", "s3"}:
        return normalized in {
            "waitbuy_over_threshold",
            "buy_over_threshold",
            "do_song_state_s2",
            "do_song_state_s3",
            "do_song_phase_chan_song",
        }
    return False


def do_song_disabled_state(payload: DoSongAdviceIn) -> str:
    state = str((payload.engine or {}).get("maTrangThai") or "").strip().lower()
    return state if state in DISABLED_DOSONG_STATES else ""


def do_song_effective_prompt_engine(payload: DoSongAdviceIn) -> dict:
    engine = dict(payload.engine or {})
    disabled_state = do_song_disabled_state(payload)
    if not disabled_state:
        return engine

    nearest = dict(payload.nearest_engine or {})
    nearest_state = str(nearest.get("maTrangThai") or "").strip().lower()
    if nearest and nearest_state and nearest_state not in DISABLED_DOSONG_STATES:
        return {
            **nearest,
            "overriddenFrom": engine,
            "overrideReason": f"disabled_{disabled_state}_use_nearest_state",
        }

    return {
        **engine,
        "maTrangThai": "SN",
        "pha": None,
        "tieuDe": "Th\u1ecb tr\u01b0\u1eddng \u0111ang trung t\u00ednh",
        "dienGiai": "T\u00edn hi\u1ec7u s\u00f3ng ch\u01b0a r\u00f5 r\u00e0ng sau khi t\u00e1ch ri\u00eang \u0111i\u1ec1u ki\u1ec7n Ch\u1edd mua v\u00e0 Mua. C\u1ea7n theo d\u00f5i th\u00eam d\u1eef li\u1ec7u v\u00f2ng tr\u00f2n d\u00f2 s\u00f3ng \u0111\u1ec3 x\u00e1c nh\u1eadn tr\u1ea1ng th\u00e1i m\u1edbi.",
        "hanhDong": "Theo d\u00f5i ti\u1ebfp v\u00e0 ch\u1edd tr\u1ea1ng th\u00e1i h\u1ec7 th\u1ed1ng r\u00f5 r\u00e0ng h\u01a1n.",
        "disabledFrom": {
            "maTrangThai": engine.get("maTrangThai"),
            "pha": engine.get("pha"),
            "tieuDe": engine.get("tieuDe"),
        },
        "disabledReason": "s2_s3_engine_conditions_disabled",
    }


def do_song_engine_signal_keys(payload: DoSongAdviceIn) -> list[str]:
    engine = do_song_effective_prompt_engine(payload)
    keys = ["do_song_engine"]
    ma_trang_thai = str(engine.get("maTrangThai") or "").strip().lower()
    if ma_trang_thai and ma_trang_thai not in DISABLED_DOSONG_STATES:
        keys.append(f"do_song_state_{ma_trang_thai}")

    pha = normalize_chat_text(str(engine.get("pha") or ""))
    phase_map = {
        "dieu chinh": "dieu_chinh",
        "tich luy": "tich_luy",
        "chan song": "chan_song",
        "song tang": "song_tang",
        "phan phoi": "phan_phoi",
    }
    if pha in phase_map and ma_trang_thai not in DISABLED_DOSONG_STATES:
        keys.append(f"do_song_phase_{phase_map[pha]}")

    return unique_signal_keys(keys)


def do_song_entry_signal_keys(payload: DoSongAdviceIn) -> list[str]:
    return []


def do_song_advice_signal_keys(payload: DoSongAdviceIn) -> list[str]:
    payload_keys = [
        key
        for key in unique_signal_keys(payload.signal_keys or [])
        if key not in {"buy_over_threshold", "waitbuy_over_threshold"}
        and not disabled_do_song_signal_key(key, payload)
    ]
    return unique_signal_keys([
        *do_song_entry_signal_keys(payload),
        *payload_keys,
        *do_song_engine_signal_keys(payload),
    ])


def resolve_do_song_condition_key(condition_logic: str) -> str:
    raw = str(condition_logic or "").strip()
    normalized = normalize_chat_text(raw)
    compact = normalized.replace(" ", "_")

    if compact in {
        "do_song_engine",
        "do_song_state_s0", "do_song_state_s1", "do_song_state_s4",
        "do_song_state_s5", "do_song_state_s6", "do_song_state_s7", "do_song_state_sn",
        "do_song_phase_dieu_chinh", "do_song_phase_tich_luy",
        "do_song_phase_song_tang", "do_song_phase_phan_phoi",
    }:
        return compact

    for state in ("s0", "s1", "s4", "s5", "s6", "s7", "sn"):
        if "do song" in normalized and state in normalized:
            return f"do_song_state_{state}"
        if "ma trang thai" in normalized and state in normalized:
            return f"do_song_state_{state}"

    phase_aliases = {
        "dieu chinh": "dieu_chinh",
        "tich luy": "tich_luy",
        "chan song": "chan_song",
        "song tang": "song_tang",
        "phan phoi": "phan_phoi",
    }
    for label, key in phase_aliases.items():
        if ("do song" in normalized or "pha" in normalized) and label in normalized:
            return f"do_song_phase_{key}"

    if "do song" in normalized or "dosong" in normalized:
        return "do_song_engine"

    return ""


def do_song_condition_result(condition_key: str, payload: DoSongAdviceIn, template: dict | None = None) -> dict:
    current_keys = do_song_engine_signal_keys(payload)
    matched = condition_key in current_keys
    engine = do_song_effective_prompt_engine(payload)
    return {
        "ok": True,
        "matched": matched,
        "condition_key": condition_key,
        "condition": condition_key,
        "data": {
            "date": payload.check_date,
            "maTrangThai": engine.get("maTrangThai"),
            "pha": engine.get("pha"),
            "tieuDe": engine.get("tieuDe"),
        },
        "message": "Do song engine condition matched" if matched else "Do song engine condition not matched",
        "template_id": template.get("id") if template else None,
        "template_name": template.get("name") if template else None,
    }


def do_song_condition_context(payload: DoSongAdviceIn, condition_key: str) -> dict:
    wave = payload.wave or {}
    return {
        "date": payload.check_date,
        "condition_key": condition_key,
        "waitbuy": wave.get("choMua") or wave.get("waitbuy") or wave.get("cm"),
        "buy": wave.get("mua") or wave.get("buy") or wave.get("mu"),
        "waitsell": wave.get("choBan") or wave.get("waitsell") or wave.get("cb"),
        "sell": wave.get("ban") or wave.get("sell") or wave.get("ba"),
        "source": "do_song_engine",
    }


async def evaluate_do_song_prompt_flow(flow: dict, templates: list[dict], templates_by_id: dict[int, dict], payload: DoSongAdviceIn) -> tuple[bool, list[str]]:
    refs = resolve_flow_condition_refs(flow.get("expression") or "", templates)
    if not refs:
        return False, []

    condition_results = []
    matches = {}
    resolved_keys = []

    for ref in refs:
        template_id = int(ref["id"])
        template = templates_by_id.get(template_id)
        if not template:
            matches[template_id] = False
            continue

        condition_logic = template_condition_key(template)
        resolved = resolve_condition_key(condition_logic) or resolve_do_song_condition_key(condition_logic)
        if not resolved:
            matches[template_id] = False
            continue

        resolved_keys.append(resolved)
        entry_keys = do_song_entry_signal_keys(payload)
        if resolved in {"buy_over_threshold", "waitbuy_over_threshold"} and resolved not in entry_keys:
            result = {
                "ok": True,
                "matched": False,
                "condition_key": resolved,
                "condition": condition_logic,
                "data": {
                    "date": payload.check_date,
                    "maTrangThai": (payload.engine or {}).get("maTrangThai"),
                    "pha": (payload.engine or {}).get("pha"),
                },
                "message": "Entry condition is only active on its matching Do Song state",
                "template_id": template_id,
                "template_name": template.get("name"),
            }
        elif resolved.startswith("do_song_"):
            result = do_song_condition_result(resolved, payload, template)
        else:
            result = await run_condition(
                template_id=template_id,
                context=do_song_condition_context(payload, condition_logic),
            )
            result["template_id"] = template_id
            result["template_name"] = template.get("name")

        matches[template_id] = bool(result.get("matched"))
        condition_results.append(result)

    return evaluate_flow_expression(flow_refs_expression(refs), matches), resolved_keys


async def find_do_song_prompt_flow(payload: DoSongAdviceIn, signal_keys: list[str]) -> dict | None:
    priority_keys = do_song_advice_signal_keys(payload)
    flows = await memory.list_condition_flows()
    templates = await memory.list_condition_templates()
    templates_by_id = {
        int(template["id"]): template
        for template in templates
        if str(template.get("id", "")).isdigit()
    }
    matched_candidates: list[tuple[int, int, dict]] = []

    for flow in flows:
        if not is_active_condition_flow(flow):
            continue

        matched, resolved_keys = await evaluate_do_song_prompt_flow(flow, templates, templates_by_id, payload)
        if not matched or not resolved_keys:
            continue

        flow_signal_key = signal_key_from_condition_keys(resolved_keys)
        priority = len(priority_keys)
        for index, desired_key in enumerate(priority_keys):
            if desired_key == flow_signal_key or desired_key in resolved_keys:
                priority = index
                break
        matched_candidates.append((priority, int(flow.get("id") or 0), flow))

    if not matched_candidates:
        return None

    matched_candidates.sort(key=lambda item: (item[0], item[1]))
    return matched_candidates[0][2]


def build_do_song_advice_prompt(payload: DoSongAdviceIn, flow: dict | None, signal_keys: list[str]) -> str:
    engine = do_song_effective_prompt_engine(payload)
    wave = payload.wave or {}
    title_prompt = str((flow or {}).get("trigger_title") or "Rewrite engine.tieuDe into the title field.").strip()
    response_prompt = str((flow or {}).get("trigger_prompt") or "Rewrite engine.dienGiai into the response field.").strip()
    recommendation_prompt = str((flow or {}).get("trigger_recommendation") or "Rewrite engine.hanhDong into the recommendation field.").strip()
    docs_prompt = combine_trigger_docs((flow or {}).get("trigger_docs"), (flow or {}).get("trigger_docs_file_text")) if flow else ""

    return "\n".join([
        "Return one valid JSON object only, no markdown, with exactly 3 string fields: title, response, recommendation.",
        "The Do Song engine output is the source of truth. Do not change maTrangThai, pha, or the core meaning.",
        "Field mapping must be followed:",
        "- title = rewrite engine.tieuDe using the title prompt and docs.",
        "- response = rewrite engine.dienGiai using the response prompt and docs.",
        "- recommendation = rewrite engine.hanhDong using the recommendation prompt and docs.",
        "Do not copy prompts or docs verbatim; use them only for tone, vocabulary, and StockTradersAI context.",
        "Terminology rule: Cho mua/Ch? mua is a signal level, not ticker count. Say Ch? mua ??t m?c X or Ch? mua ? m?c X; never say X m? or X c? phi?u for Ch? mua.",
        "Temporary rule: raw S2/S3 are disabled in Do Song engine. If disabledReason is s2_s3_engine_conditions_disabled, do not use waitbuy/buy as the main signal and do not write an S2/S3 entry-confirmation view; write a neutral do_song_engine view only.",
        build_signal_card_length_instruction(strict=False),
        "Selected step-3 prompts and docs:",
        json.dumps({
            "flow_id": (flow or {}).get("id"),
            "flow_name": (flow or {}).get("name"),
            "signal_keys": signal_keys,
            "title_prompt": title_prompt,
            "response_prompt": response_prompt,
            "recommendation_prompt": recommendation_prompt,
            "docs": compact_signal_text(docs_prompt, "", max_chars=8000),
        }, ensure_ascii=False),
        "Do Song engine context:",
        json.dumps({
            "check_date": payload.check_date,
            "wave": wave,
            "engine": {
                "maTrangThai": engine.get("maTrangThai"),
                "pha": engine.get("pha"),
                "tieuDe": engine.get("tieuDe"),
                "dienGiai": engine.get("dienGiai"),
                "hanhDong": engine.get("hanhDong"),
                "tinCay": engine.get("tinCay"),
                "dacTrung": engine.get("dacTrung"),
                "overrideReason": engine.get("overrideReason"),
                "disabledReason": engine.get("disabledReason"),
            },
        }, ensure_ascii=False),
    ])

@app.post("/public/do-song-advice")
async def public_do_song_advice(payload: DoSongAdviceIn):
    fallback = do_song_advice_fallback(payload)
    signal_keys = do_song_advice_signal_keys(payload)
    flow = await find_do_song_prompt_flow(payload, signal_keys)
    raw_engine = payload.raw_engine or payload.engine or {}
    engine = do_song_effective_prompt_engine(payload)
    disabled_state = do_song_disabled_state(payload)

    try:
        client = OpenAIClient()
        resp = client.chat(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are StockTraders AI. Write concise Vietnamese market advice based strictly on the provided Do Song engine output. In the visible fields title, response, and recommendation, use Vietnamese only and do not use English words such as engine, market, raw, disabled, signal, status, entry, confirmation, waitbuy, or buy.",
                },
                {"role": "user", "content": build_do_song_advice_prompt(payload, flow, signal_keys)},
            ],
            tools=None,
            tool_choice="auto",
        )
        content = (resp.choices[0].message.content or "").strip()
        card = parse_signal_card_ai_content(content, fallback)
    except Exception as exc:
        print("DO_SONG_ADVICE_ERROR:", exc)
        card = fallback

    return {
        "ok": True,
        "title": card.get("title"),
        "response": card.get("response"),
        "recommendation": card.get("recommendation"),
        "check_date": payload.check_date or None,
        "source": "do_song_engine",
        "flow_id": flow.get("id") if flow else None,
        "signal_keys": signal_keys,
        "maTrangThai": engine.get("maTrangThai"),
        "pha": engine.get("pha"),
        "raw_maTrangThai": raw_engine.get("maTrangThai") if disabled_state else None,
        "raw_pha": raw_engine.get("pha") if disabled_state else None,
        "disabled_state": disabled_state or None,
    }

@app.get("/public/condition-signals/latest")
async def public_latest_condition_signal(
    signal_key: Optional[str] = None,
    flow_id: Optional[int] = None,
    check_date: Optional[str] = None,
    date: Optional[str] = None,
    waitbuy: Optional[str] = None,
    buy: Optional[str] = None,
):
    signal_key = normalize_public_signal_key(signal_key)
    requested_check_date = (check_date or date or "").strip()
    requested_metric = signal_wave_metric(signal_key)
    requested_metric_value = parse_public_float(buy if requested_metric == "buy" else waitbuy)
    signal = await memory.get_latest_condition_signal(
        signal_key=signal_key,
        flow_id=flow_id,
        check_date=requested_check_date or None,
    )
    if requested_check_date and (
        not signal
        or signal_card_length_too_short(signal)
        or (
            requested_metric_value is not None
            and not cached_signal_wave_metric_matches(signal, requested_metric, requested_metric_value)
        )
    ):
        signal = await build_public_historical_wave_signal(
            requested_signal_key=signal_key,
            requested_flow_id=flow_id,
            check_date=requested_check_date,
            metric_value=requested_metric_value,
        )
    title = signal.get("title") if signal else None
    response = signal.get("message") if signal else None
    recommendation = signal.get("recommendation") if signal else None

    if signal and not requested_check_date:
        state = await memory.get_condition_signal_state(
            int(signal.get("flow_id")),
            signal.get("signal_key") or signal_key or "",
        )
        state_updated_at = state.get("updated_at")
        signal_updated_at = signal.get("updated_at")

        if (
            state_updated_at
            and signal_updated_at
            and not state.get("matched")
            and str(state_updated_at) >= str(signal_updated_at)
        ):
            title = None
            response = None
            recommendation = None

    return {
        "ok": True,
        "title": title,
        "response": response,
        "recommendation": recommendation,
        "check_date": signal.get("check_date") if signal else None,
    }


@app.get("/public/condition-signals")
async def public_condition_signals(
    signal_key: Optional[str] = None,
    flow_id: Optional[int] = None,
    check_date: Optional[str] = None,
    date: Optional[str] = None,
    limit: int = 20,
):
    return {
        "ok": True,
        "signals": await memory.list_condition_signals(
            signal_key=normalize_public_signal_key(signal_key),
            flow_id=flow_id,
            check_date=(check_date or date or "").strip() or None,
            limit=limit,
        ),
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
        docs=payload.docs.strip(),
        docs_file_text=payload.docs_file_text.strip(),
        docs_file_names=payload.docs_file_names.strip(),
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
        docs=payload.docs.strip(),
        docs_file_text=payload.docs_file_text.strip(),
        docs_file_names=payload.docs_file_names.strip(),
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

    next_status = "waiting" if case.get("status") == "supported" else "supported"
    await memory.set_case_idea_status(case_id, next_status)

    return {"ok": True, "status": next_status}


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
    return FileResponse(
        os.path.join(FRONTEND_DIR, path),
        headers={"Cache-Control": "no-store"},
    )

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
        print("SALES_ROUTE_DECISION:", {
            "user_id": payload.user_id,
            "stage": state.get("stage"),
            "route": route,
            "message": payload.message,
        })
        if route == "normal":
            print("SALES_NORMAL_STREAM_START:", {"user_id": payload.user_id, "message": payload.message})
            done_data = {}
            async for event, data in stream_standard_chat(
                orch,
                user_id=payload.user_id,
                user_text=payload.message,
                language=payload.language,
                selected_model=payload.model,
            ):
                print("SALES_NORMAL_STREAM_EVENT:", {
                    "event": event,
                    "keys": list((data or {}).keys()) if isinstance(data, dict) else [],
                    "sources": (data or {}).get("sources") if isinstance(data, dict) else None,
                    "text_len": len(str((data or {}).get("text") or "")) if isinstance(data, dict) else 0,
                })
                if event == "done":
                    done_data = data
                    print("SALES_NORMAL_CAPTURE_DONE:", done_data)
                    continue
                yield event, data

            done_sources = (done_data or {}).get("sources") or []
            print("SALES_NORMAL_DONE_SOURCES:", done_sources)
            if done_sources:
                print("SALES_NORMAL_RETURN_DONE_EARLY:", done_data)
                yield "done", done_data
                return

            if state["stage"] != "completed":
                print("SALES_NORMAL_FOLLOW_UP_START:", {"user_id": payload.user_id, "message": payload.message})
                try:
                    follow_up = await sales.next_collection_question_ai(
                        state["targets"],
                        state.get("target_configs"),
                        user_text=payload.message,
                        history=recent_history,
                    )
                except Exception as exc:
                    print("SALES_FOLLOW_UP_ERROR:", exc)
                    follow_up = None
                print("SALES_NORMAL_FOLLOW_UP_RESULT:", {"has_follow_up": bool(follow_up), "len": len(follow_up or "")})
                if follow_up:
                    text = "\n\n" + follow_up
                    for i in range(0, len(text), 60):
                        chunk = text[i:i + 60]
                        if chunk:
                            yield "delta", {"text": chunk}
                    await memory.add(payload.user_id, "assistant", follow_up)

            print("SALES_NORMAL_RETURN_DONE_FINAL:", done_data)
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

    async for event, data in stream_standard_chat(
        orch,
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

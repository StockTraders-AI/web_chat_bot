import asyncio
import uuid
from contextvars import ContextVar

from openai import OpenAI
from settings import OPENAI_API_KEY


_TOKEN_USAGE_CONTEXT: ContextVar[dict | None] = ContextVar(
    "openai_token_usage_context",
    default=None,
)


def reset_token_usage():
    _TOKEN_USAGE_CONTEXT.set({
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })


def current_token_usage():
    usage = _TOKEN_USAGE_CONTEXT.get()
    if not usage:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    return dict(usage)


def _add_token_usage(prompt_tokens: int, completion_tokens: int, total_tokens: int):
    usage = _TOKEN_USAGE_CONTEXT.get()
    if usage is None:
        return

    usage["prompt_tokens"] += int(prompt_tokens or 0)
    usage["completion_tokens"] += int(completion_tokens or 0)
    usage["total_tokens"] += int(total_tokens or 0)


async def _persist_ai_usage_event(route: str, model: str, usage: dict):
    """Ghi 1 lan goi OpenAI vao ai_token_usage_events, gan nhan "route" =
    tinh nang nao trong app da goi (Khuyen nghi tu AI, Tu van AI...), de co
    the xem duoc quota API key bi tieu vao dau. Fire-and-forget: khong duoc
    lam fail request goc chi vi ghi log that bai. Import memory tre (luc goi,
    khong phai luc module nap) de tranh vong lap import voi main.py."""
    try:
        from main import memory

        await memory.record_ai_token_usage(
            tenant_id="system",
            user_id="system",
            user_key=route,
            conversation_id="-",
            request_id=str(uuid.uuid4()),
            route=route,
            model=model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )
    except Exception as exc:
        print(f"AI_USAGE_EVENT_LOG_FAILED route={route}: {exc}")


def _schedule_ai_usage_event(route: str, model: str, usage: dict):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_persist_ai_usage_event(route, model, usage))
    except RuntimeError:
        # Khong co event loop dang chay (vd goi tu script/test) - bo qua log,
        # khong lam fail cuoc goi AI chi vi thieu tracking.
        pass


class OpenAIClient:

    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is empty")

        self.client = OpenAI(api_key=OPENAI_API_KEY)

    def chat(self, model: str, messages, tools=None, tool_choice="auto", route: str = "unspecified"):

        params = {
            "model": model,
            "messages": messages
        }

        if isinstance(tools, list) and len(tools) > 0:
            params["tools"] = tools
            params["tool_choice"] = tool_choice

        resp = self.client.chat.completions.create(**params)

        if hasattr(resp, "usage") and resp.usage:
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }
            _add_token_usage(**usage)
            _schedule_ai_usage_event(route, model, usage)
            print("TOKEN USAGE:", usage, "route:", route)

        return resp

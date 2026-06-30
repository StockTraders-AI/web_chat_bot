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


class OpenAIClient:

    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is empty")

        self.client = OpenAI(api_key=OPENAI_API_KEY)

    def chat(self, model: str, messages, tools=None, tool_choice="auto"):

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
            print("TOKEN USAGE:", usage)

        return resp

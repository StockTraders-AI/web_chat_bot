from openai import OpenAI
from settings import OPENAI_API_KEY


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

        # chỉ thêm tools khi thực sự có tool hợp lệ
        if isinstance(tools, list) and len(tools) > 0:
            params["tools"] = tools
            params["tool_choice"] = tool_choice

        resp = self.client.chat.completions.create(**params)

        if hasattr(resp, "usage") and resp.usage:
            print("TOKEN USAGE:", {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            })

        return resp


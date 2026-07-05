import json
import os
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from routes import portfolio_chat as route
from services.ticker_policy import find_disallowed_tickers


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    async def chat_stream(self, **kwargs):
        self.calls.append(kwargs)
        yield "delta", {"text": "BVS dang dung song dung nganh."}
        yield "done", {
            "sources": [],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        }


class PortfolioChatAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.orchestrator = FakeOrchestrator()
        route.configure_portfolio_chat_api(lambda: self.orchestrator)

    def sample_portfolio(self):
        return {
            "score": 75,
            "counts": {"dd": 3, "ds": 1, "sd": 0, "ss": 1},
            "positions": [
                {
                    "ticker": "BVS",
                    "industry": "Chung khoan",
                    "smdt": 128.3,
                    "branchSmdt": 96.2,
                    "cat": "dd",
                    "tickerSig": "si",
                    "branchSig": "sn",
                }
            ],
        }

    def test_builds_standard_chat_input_with_portfolio_context(self):
        text = route.build_portfolio_chat_text("Ma nao dung song?", self.sample_portfolio())

        self.assertIn("Ma nao dung song?", text)
        self.assertIn('"ticker":"BVS"', text)
        self.assertIn("web chat StockTraders AI", text)
        self.assertEqual(find_disallowed_tickers(text), [])

    async def test_portfolio_chat_route_uses_shared_chat_runtime(self):
        payload = route.PortfolioChatIn(
            question="Ma nao dung song?",
            portfolio=self.sample_portfolio(),
            user_id="u1",
            conversation_id="p1",
            model="gpt-4o",
        )

        result = await route.portfolio_chat(payload, x_api_key=None)

        self.assertEqual(result["answer"], "BVS dang dung song dung nganh.")
        self.assertEqual(result["usage"]["total_tokens"], 120)
        self.assertEqual(result["conversation_id"], "p1")
        self.assertEqual(len(self.orchestrator.calls), 1)
        call = self.orchestrator.calls[0]
        self.assertEqual(call["user_id"], "portfolio:u1:p1")
        self.assertEqual(call["selected_model"], "gpt-4o")
        self.assertIn('"ticker":"BVS"', call["user_text"])
        self.assertIn("Ma nao dung song?", call["user_text"])

    async def test_portfolio_chat_api_key_is_optional_but_enforced_when_set(self):
        payload = route.PortfolioChatIn(
            question="Ma nao dung song?",
            portfolio=self.sample_portfolio(),
        )

        old_value = os.environ.get("PORTFOLIO_CHAT_API_KEY")
        os.environ["PORTFOLIO_CHAT_API_KEY"] = "secret"
        try:
            with self.assertRaises(HTTPException) as ctx:
                await route.portfolio_chat(payload, x_api_key=None)
            self.assertEqual(ctx.exception.status_code, 401)
        finally:
            if old_value is None:
                os.environ.pop("PORTFOLIO_CHAT_API_KEY", None)
            else:
                os.environ["PORTFOLIO_CHAT_API_KEY"] = old_value


if __name__ == "__main__":
    unittest.main()
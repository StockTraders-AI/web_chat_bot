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
        text = route.build_portfolio_chat_text("BVS thuộc nhóm 4 key nào?", self.sample_portfolio())

        self.assertIn("4 key", text)
        self.assertIn('"ticker":"BVS"', text)
        self.assertIn("web chat StockTraders AI", text)
        self.assertEqual(find_disallowed_tickers(text), [])

    def test_regular_data_questions_ignore_portfolio_context(self):
        question = "FTS đạt chuẩn mã mạnh thế nào trong tháng 6"

        user_text, uses_context = route.build_chat_input(question, self.sample_portfolio())

        self.assertFalse(uses_context)
        self.assertEqual(user_text, question)
        self.assertNotIn("Portfolio JSON", user_text)

    def test_4key_score_questions_use_portfolio_context(self):
        question = "BVS thuộc nhóm 4 key nào?"

        user_text, uses_context = route.build_chat_input(question, self.sample_portfolio())

        self.assertTrue(uses_context)
        self.assertIn("Portfolio JSON", user_text)
        self.assertIn('"ticker":"BVS"', user_text)

    async def test_portfolio_chat_route_uses_shared_chat_runtime_for_4key_context(self):
        payload = route.PortfolioChatIn(
            question="BVS thuộc nhóm 4 key nào?",
            portfolio=self.sample_portfolio(),
            user_id="u1",
            conversation_id="p1",
            model="gpt-4o",
        )

        result = await route.portfolio_chat(payload, x_api_key=None)

        self.assertEqual(result["answer"], "BVS dang dung song dung nganh.")
        self.assertEqual(result["usage"]["total_tokens"], 120)
        self.assertEqual(result["conversation_id"], "p1")
        call = self.orchestrator.calls[0]
        self.assertEqual(call["user_id"], "portfolio:u1:p1")
        self.assertEqual(call["selected_model"], "gpt-4o")
        self.assertTrue(call["skip_question_guide"])
        self.assertIn('"ticker":"BVS"', call["user_text"])

    async def test_portfolio_chat_route_does_not_send_portfolio_for_regular_data_question(self):
        payload = route.PortfolioChatIn(
            question="FTS đạt chuẩn mã mạnh thế nào trong tháng 6",
            portfolio=self.sample_portfolio(),
            user_id="u1",
            conversation_id="p1",
            model="gpt-4o",
        )

        await route.portfolio_chat(payload, x_api_key=None)

        call = self.orchestrator.calls[0]
        self.assertEqual(call["user_text"], "FTS đạt chuẩn mã mạnh thế nào trong tháng 6")
        self.assertNotIn("skip_question_guide", call)

    async def test_portfolio_chat_api_key_is_optional_but_enforced_when_set(self):
        payload = route.PortfolioChatIn(
            question="BVS thuộc nhóm 4 key nào?",
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
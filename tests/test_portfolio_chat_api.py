import os
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from routes import portfolio_chat as route


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
            "asOfDate": "2026-07-04",
            "score": 75,
            "counts": {"dd": 3, "ds": 1, "sd": 0, "ss": 1},
            "positions": [
                {
                    "ticker": "BVS",
                    "industry": "Chung khoan",
                    "smdt": 128.3,
                    "smdtPrev": 68.4,
                    "branchSmdt": 96.2,
                    "branchSmdtPrev": 40.1,
                    "cat": "dd",
                }
            ],
        }

    def test_build_chat_input_ignores_portfolio_context(self):
        question = "BVS thuoc nhom 4 key nao?"

        user_text, uses_context = route.build_chat_input(question, self.sample_portfolio())

        self.assertFalse(uses_context)
        self.assertEqual(user_text, question)
        self.assertNotIn("Portfolio JSON", user_text)
        self.assertNotIn('"ticker":"BVS"', user_text)

    async def test_portfolio_chat_route_always_uses_shared_chat_runtime(self):
        payload = route.PortfolioChatIn(
            question="BVS thuoc nhom 4 key nao?",
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
        self.assertEqual(call["user_text"], "BVS thuoc nhom 4 key nao?")
        self.assertEqual(call["selected_model"], "gpt-4o")

    async def test_portfolio_chat_route_does_not_require_portfolio(self):
        payload = route.PortfolioChatIn(
            question="SMDT GEX hien nay la bao nhieu?",
            user_id="u1",
            conversation_id="p1",
        )

        await route.portfolio_chat(payload, x_api_key=None)

        call = self.orchestrator.calls[0]
        self.assertEqual(call["user_text"], "SMDT GEX hien nay la bao nhieu?")

    async def test_portfolio_chat_answers_single_position_dd(self):
        payload = route.PortfolioChatIn(
            question="Mã nào đúng sóng, đúng ngành?",
            portfolio={
                "asOfDate": "2026-07-31",
                "position": {
                    "ticker": "BVS",
                    "industry": "Chung khoan",
                    "smdt": 128.3,
                    "smdtPrev": 68.4,
                    "branchSmdt": 96.2,
                    "branchSmdtPrev": 40.1,
                    "cat": "dd",
                },
            },
            user_id="u1",
            conversation_id="p1",
        )

        result = await route.portfolio_chat(payload, x_api_key=None)

        self.assertEqual(result["answer"], "BVS")
        self.assertEqual(self.orchestrator.calls, [])

    async def test_portfolio_chat_answers_single_position_non_dd(self):
        payload = route.PortfolioChatIn(
            question="Mã nào đúng sóng, đúng ngành?",
            portfolio={
                "position": {
                    "ticker": "DIG",
                    "cat": "ds",
                },
            },
            user_id="u1",
            conversation_id="p1",
        )

        result = await route.portfolio_chat(payload, x_api_key=None)

        self.assertEqual(result["answer"], "Không có mã nào đúng sóng đúng ngành trong mã được gửi.")
        self.assertEqual(self.orchestrator.calls, [])
    async def test_portfolio_chat_answers_single_position_ss(self):
        payload = route.PortfolioChatIn(
            question="Mã nào sai sóng, sai ngành?",
            portfolio={"position": {"ticker": "BVS", "cat": "ss"}},
            user_id="u1",
            conversation_id="p1",
        )

        result = await route.portfolio_chat(payload, x_api_key=None)

        self.assertEqual(result["answer"], "BVS")
        self.assertEqual(self.orchestrator.calls, [])
    async def test_portfolio_chat_api_key_is_optional_but_enforced_when_set(self):
        payload = route.PortfolioChatIn(
            question="BVS thuoc nhom 4 key nao?",
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

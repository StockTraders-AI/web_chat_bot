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
        yield "delta", {"text": "BVS \u0111ang \u0111\u00fang s\u00f3ng \u0111\u00fang ng\u00e0nh."}
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
        self.assertIn("Ng\u00e0y \u0111\u00e1nh gi\u00e1 b\u1eaft bu\u1ed9c l\u00e0 2026-07-04", text)
        self.assertIn("kh\u00f4ng \u0111\u01b0\u1ee3c t\u1ef1 \u0111\u1ed5i sang ng\u00e0y hi\u1ec7n t\u1ea1i", text)
        self.assertIn("Kh\u00f4ng \u0111\u01b0\u1ee3c tr\u00ecnh b\u00e0y ph\u00e9p suy lu\u1eadn fallback", text)
        self.assertNotIn("SMDT m\u00e3 t\u0103ng l\u00e0 m\u00e3 \u0111\u00fang s\u00f3ng", text)
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

    def test_simple_4key_answer_can_be_derived_from_smdt_deltas(self):
        portfolio = self.sample_portfolio()
        portfolio["positions"][0].pop("cat")

        answer = route.build_simple_four_key_answer("BVS thuoc nhom 4 key nao?", portfolio)

        self.assertEqual(answer, "Nh\u00f3m 4 Key: \"\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh\"")

    async def test_portfolio_chat_route_answers_yes_no_group_question_naturally(self):
        payload = route.PortfolioChatIn(
            question="Ma nay co dung song dung nganh khong?",
            portfolio=self.sample_portfolio(),
            user_id="u1",
            conversation_id="p1",
            model="gpt-4o",
        )

        result = await route.portfolio_chat(payload, x_api_key=None)

        self.assertEqual(result["answer"], "C\u00f3, m\u00e3 n\u00e0y \u0111ang thu\u1ed9c nh\u00f3m \"\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh\".")
        self.assertEqual(result["usage"]["total_tokens"], 0)
        self.assertEqual(self.orchestrator.calls, [])

    async def test_portfolio_chat_route_answers_no_when_group_does_not_match(self):
        payload = route.PortfolioChatIn(
            question="Ma nay co sai song sai nganh khong?",
            portfolio=self.sample_portfolio(),
            user_id="u1",
            conversation_id="p1",
            model="gpt-4o",
        )

        result = await route.portfolio_chat(payload, x_api_key=None)

        self.assertEqual(result["answer"], "Kh\u00f4ng, m\u00e3 n\u00e0y \u0111ang thu\u1ed9c nh\u00f3m \"\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh\".")
        self.assertEqual(result["usage"]["total_tokens"], 0)
        self.assertEqual(self.orchestrator.calls, [])

    async def test_portfolio_chat_route_returns_only_group_for_simple_4key_question(self):
        payload = route.PortfolioChatIn(
            question="BVS thuoc nhom 4 key nao?",
            portfolio=self.sample_portfolio(),
            user_id="u1",
            conversation_id="p1",
            model="gpt-4o",
        )

        result = await route.portfolio_chat(payload, x_api_key=None)

        self.assertEqual(result["answer"], "Nh\u00f3m 4 Key: \"\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh\"")
        self.assertEqual(result["usage"]["total_tokens"], 0)
        self.assertEqual(result["conversation_id"], "p1")
        self.assertEqual(self.orchestrator.calls, [])

    async def test_portfolio_chat_route_uses_shared_chat_runtime_when_asking_why(self):
        payload = route.PortfolioChatIn(
            question="Vi sao BVS thuoc nhom 4 key nay?",
            portfolio=self.sample_portfolio(),
            user_id="u1",
            conversation_id="p1",
            model="gpt-4o",
        )

        result = await route.portfolio_chat(payload, x_api_key=None)

        self.assertEqual(result["answer"], "BVS \u0111ang \u0111\u00fang s\u00f3ng \u0111\u00fang ng\u00e0nh.")
        self.assertEqual(result["usage"]["total_tokens"], 120)
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

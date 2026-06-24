import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.memory import MemoryStore
from core.question_guide import QuestionGuide


class FakeRAG:
    rule_docs = {
        "Câu hỏi về sức mạnh dòng tiền, smdt ngành, mã.txt": {
            "chunks": ['Guide Khi hỏi: "SMDT [mã] hiện tại là bao nhiêu?"']
        },
        "Câu hỏi về tín hiệu dòng tiền mã , dòng tiền mã.txt": {
            "chunks": ['Guide "Dòng tiền [mã] hiện nay thế nào?"']
        },
        "Câu hỏi về mã, cổ phiếu, đạt chuẩn mã mạnh.txt": {
            "chunks": ['Guide "Mã [X] đạt chuẩn mã mạnh từ khi nào?"']
        },
        "Câu hỏi về tín hiệu giao dịch (mua,bán), giá vốn trung bình, tỷ trọng nắm giữ, tỷ trọng giao dịch của mã.txt": {
            "chunks": ['Guide "Tín hiệu mua/bán gần nhất của [mã]"']
        },
        "Câu hỏi về giá của mã.txt": {
            "chunks": ['Guide Khi người dùng hỏi giá cổ phiếu tại thời điểm hiện tại']
        },
        "Câu hỏi về ngành, dẫn sóng, đạt chuẩn ngành mạnh.txt": {
            "chunks": ['Guide "Ngành [X] bắt đầu mạnh từ khi nào?"']
        },
    }



class FakeOpenAI:
    class _Message:
        content = "Mình có thể đi theo một trong các hướng phù hợp dưới đây.\n6. Case bịa thêm"

    class _Choice:
        message = None

    class _Response:
        choices = []

    def chat(self, **kwargs):
        choice = self._Choice()
        choice.message = self._Message()
        response = self._Response()
        response.choices = [choice]
        return response

class QuestionGuideSemanticTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "semantic.db")
        self.memory = MemoryStore(self.db_path)
        await self.memory.init()
        self.guide = QuestionGuide(FakeRAG(), memory=self.memory)

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_broad_stock_question_uses_rule_cases(self):
        result = await self.guide.handle("u1", "co nen mua acb ko")
        self.assertEqual(result.action, "ask")
        self.assertIn("SMDT ACB hiện tại là bao nhiêu?", result.message)
        self.assertIn("Dòng tiền ACB hiện nay thế nào?", result.message)

    async def test_gpt_only_writes_intro_and_cannot_add_cases(self):
        guide = QuestionGuide(FakeRAG(), memory=self.memory, openai_client=FakeOpenAI())
        result = await guide.handle("gpt1", "co nen mua ACB ko")
        self.assertIn("Mình có thể đi theo", result.message)
        self.assertNotIn("Case bịa thêm", result.message)
        self.assertEqual(result.message.count("\n"), 5)
    async def test_specific_rule_case_runs_instead_of_generic_chat(self):
        result = await self.guide.handle("rule1", "ACB có đạt chuẩn mã mạnh không?")
        self.assertEqual(result.action, "run")
        self.assertEqual(result.canonical_question, "ACB có đạt chuẩn mã mạnh không?")
    async def test_new_question_does_not_select_price_from_tham_gia(self):
        await self.guide.handle("route1", "co nen mua DAN ko")
        result = await self.guide.handle("route1", "lộ trình các dòng tham gia dẫn sóng 3/2026")
        self.assertEqual(result.action, "pass")
        self.assertEqual(result.canonical_question, "")

    async def test_price_alias_still_selects_price_suggestion(self):
        await self.guide.handle("route2", "co nen mua DAN ko")
        result = await self.guide.handle("route2", "giá")
        self.assertEqual(result.action, "run")
        self.assertEqual(result.canonical_question, "Giá DAN hiện nay là bao nhiêu?")
    async def test_selected_case_survives_question_guide_restart(self):
        await self.guide.handle("u2", "co nen mua ACB ko")
        restarted = QuestionGuide(FakeRAG(), memory=self.memory)
        result = await restarted.handle("u2", "2")
        self.assertEqual(result.action, "run")
        self.assertEqual(result.canonical_question, "Dòng tiền ACB hiện nay thế nào?")

    async def test_waitbuy_accepts_dash_date_follow_up(self):
        year = datetime.now().year
        first = await self.guide.handle("u3", "cho mua thang 3 bao nhieu")
        second = await self.guide.handle("u3", "15-3 đi")
        self.assertEqual(first.action, "ask")
        self.assertEqual(second.canonical_question, f"Chờ mua ngày 15/03/{year} là bao nhiêu?")

    async def test_wave_month_follow_up(self):
        year = datetime.now().year
        await self.guide.handle("u4", "chan song gan nhat la bao nhieu")
        result = await self.guide.handle("u4", "thang 4")
        self.assertEqual(result.canonical_question, f"Trong tháng 4/{year}, ngày nào xác nhận chân sóng?")

    async def test_colloquial_buy_question_is_guided(self):
        result = await self.guide.handle("u5", "muc acb on khong")
        self.assertEqual(result.action, "ask")
        self.assertIn("ACB", result.message)

    async def test_missing_ticker_is_collected_then_routed(self):
        first = await self.guide.handle("u6", "phan tich co phieu")
        second = await self.guide.handle("u6", "ACB")
        self.assertEqual(first.action, "ask")
        self.assertIn("mã cổ phiếu", first.message)
        self.assertEqual(second.action, "ask")
        self.assertIn("ACB", second.message)

    async def test_missing_branch_is_collected_then_routed(self):
        first = await self.guide.handle("u7", "phan tich nganh")
        second = await self.guide.handle("u7", "ngân hàng")
        self.assertEqual(first.action, "ask")
        self.assertIn("ngành", first.message)
        self.assertEqual(second.action, "ask")
        self.assertIn("ngân hàng", second.message)

    async def test_ambiguous_smdt_asks_stock_or_branch(self):
        first = await self.guide.handle("u9", "smdt hôm nay")
        second = await self.guide.handle("u9", "ACB")
        self.assertEqual(first.action, "ask")
        self.assertIn("mã cổ phiếu", first.message)
        self.assertEqual(second.canonical_question, "SMDT ACB hiện nay là bao nhiêu?")

    async def test_subject_then_time_are_collected_in_sequence(self):
        first = await self.guide.handle("u10", "smdt tháng")
        second = await self.guide.handle("u10", "ngành ngân hàng")
        third = await self.guide.handle("u10", "tháng 5")
        self.assertEqual(first.action, "ask")
        self.assertEqual(second.action, "ask")
        self.assertEqual(third.action, "run")
        self.assertEqual(third.canonical_question, f"SMDT ngành ngân hàng tháng 5/{datetime.now().year} là bao nhiêu?")
    async def test_missing_waitbuy_time_is_collected(self):
        first = await self.guide.handle("u8", "cho mua bao nhieu")
        second = await self.guide.handle("u8", "hom nay")
        self.assertEqual(first.action, "ask")
        self.assertEqual(second.action, "run")
        self.assertEqual(second.canonical_question, "Chờ mua hôm nay là bao nhiêu?")


if __name__ == "__main__":
    unittest.main()
import unittest

from backend.core.question_guide import QuestionGuide


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
    }


class QuestionGuideSemanticTests(unittest.TestCase):
    def setUp(self):
        self.guide = QuestionGuide(FakeRAG())

    def test_broad_stock_question_uses_rule_cases(self):
        result = self.guide.handle("u1", "co nen mua acb ko")
        self.assertEqual(result.action, "ask")
        self.assertIn("SMDT ACB hiện tại là bao nhiêu?", result.message)
        self.assertIn("Dòng tiền ACB hiện nay thế nào?", result.message)

    def test_colloquial_buy_question_is_guided(self):
        result = self.guide.handle("u5", "muc acb on khong")
        self.assertEqual(result.action, "ask")
        self.assertIn("ACB", result.message)
    def test_selected_case_keeps_pending_context(self):
        self.guide.handle("u2", "co nen mua ACB ko")
        result = self.guide.handle("u2", "2")
        self.assertEqual(result.action, "run")
        self.assertEqual(result.canonical_question, "Dòng tiền ACB hiện nay thế nào?")

    def test_waitbuy_accepts_dash_date_follow_up(self):
        first = self.guide.handle("u3", "cho mua thang 3 bao nhieu")
        second = self.guide.handle("u3", "15-3 đi")
        self.assertEqual(first.action, "ask")
        self.assertEqual(second.canonical_question, "Chờ mua ngày 15/03/2026 là bao nhiêu?")

    def test_wave_month_follow_up(self):
        self.guide.handle("u4", "chan song gan nhat la bao nhieu")
        result = self.guide.handle("u4", "thang 4")
        self.assertEqual(result.canonical_question, "Trong tháng 4/2026, ngày nào xác nhận chân sóng?")


if __name__ == "__main__":
    unittest.main()
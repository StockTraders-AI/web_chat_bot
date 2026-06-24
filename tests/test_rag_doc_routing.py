import unittest

from core.rag import RAGStore


class RAGDocumentRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_strong_stock_question_selects_strong_stock_rule(self):
        rag = RAGStore.__new__(RAGStore)
        rag.rule_docs = {
            "Câu hỏi về lịch sử mua bán của một mã.txt": {},
            "Câu hỏi về mã, cổ phiếu, đạt chuẩn mã mạnh.txt": {},
            "Câu hỏi về ngành, dẫn sóng, đạt chuẩn ngành mạnh.txt": {},
        }

        selected = await rag.pick_doc("Mã ACB bắt đầu mạnh từ khi nào?")

        self.assertEqual(
            selected,
            "Câu hỏi về mã, cổ phiếu, đạt chuẩn mã mạnh.txt",
        )

    async def test_strong_branch_question_selects_strong_branch_rule(self):
        rag = RAGStore.__new__(RAGStore)
        rag.rule_docs = {
            "Câu hỏi về mã, cổ phiếu, đạt chuẩn mã mạnh.txt": {},
            "Câu hỏi về ngành, dẫn sóng, đạt chuẩn ngành mạnh.txt": {},
        }

        selected = await rag.pick_doc("Ngành ngân hàng có đạt chuẩn ngành mạnh không?")

        self.assertEqual(
            selected,
            "Câu hỏi về ngành, dẫn sóng, đạt chuẩn ngành mạnh.txt",
        )
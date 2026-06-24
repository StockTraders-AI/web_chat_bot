import unittest

from core.rag import RAGStore


class RAGDocumentRoutingTests(unittest.IsolatedAsyncioTestCase):
    def test_branch_smdt_selects_branch_metric_chunk(self):
        rag = RAGStore.__new__(RAGStore)
        chunks = [
            'Guide "SMDT các ngành chủ lực ngày [date]". Gọi getSMDTBranch cho các ngành chủ lực.',
            'Guide Khi hỏi: "SMDT [ngành] là bao nhiêu?". Gọi getSMDTBranch với ngành và date được hỏi.',
            'Guide "SMDT các mã dòng [ngành] của [ngày]". Gọi getBranchPath rồi gọi getSMDTTicker từng mã.',
        ]

        context = rag.build_context(
            "Câu hỏi về sức mạnh dòng tiền, smdt ngành, mã.txt",
            chunks,
            "SMDT dòng chứng khoán ngày 9/4/2025",
            max_chunks=1,
        )

        self.assertIn("SMDT [ngành]", context["refs"])
        self.assertIn("getSMDTBranch", context["refs"])
        self.assertNotIn("ngành chủ lực", context["refs"])
        self.assertNotIn("getBranchPath", context["refs"])

    def test_branch_tickers_selects_ticker_collection_chunk(self):
        rag = RAGStore.__new__(RAGStore)
        chunks = [
            'Guide Khi hỏi: "SMDT [ngành] là bao nhiêu?". Gọi getSMDTBranch với ngành và date được hỏi.',
            'Guide "SMDT các mã dòng [ngành] của [ngày]". Gọi getBranchPath rồi gọi getSMDTTicker từng mã.',
        ]

        context = rag.build_context(
            "Câu hỏi về sức mạnh dòng tiền, smdt ngành, mã.txt",
            chunks,
            "SMDT các mã dòng chứng khoán ngày 9/4/2025",
            max_chunks=1,
        )

        self.assertIn("getBranchPath", context["refs"])
        self.assertIn("getSMDTTicker", context["refs"])
    def test_specific_digit_ticker_strong_query_selects_latest_cross_chunk(self):
        rag = RAGStore.__new__(RAGStore)
        chunks = [
            'Guide "Mã [X] đạt chuẩn mã mạnh từ khi nào?" Gọi getSMDTTickerCross với keyValue=[mã], không truyền date.',
            'Guide "Mã nào đạt chuẩn mã mạnh vào tháng mm-yyyy hoặc năm yyyy". Gọi getSMDTTickerCross với date.',
            'Guide Giá và SMDT cùng ngày. Gọi getTotalTradeWithSMDT.',
        ]

        context = rag.build_context(
            "Câu hỏi về mã, cổ phiếu, đạt chuẩn mã mạnh.txt",
            chunks,
            "PC1 đạt chuẩn mã mạnh khi nào",
            max_chunks=1,
        )

        self.assertIn("keyValue=[mã]", context["refs"])
        self.assertIn("không truyền date", context["refs"])
        self.assertNotIn("getTotalTradeWithSMDT", context["refs"])
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
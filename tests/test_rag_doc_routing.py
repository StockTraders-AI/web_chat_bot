import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.rag import RAGStore


class RAGDocumentRoutingTests(unittest.IsolatedAsyncioTestCase):
    def test_song_lon_definition_selects_hdsd_book(self):
        rag = RAGStore.__new__(RAGStore)
        rag.book_docs = {
            "HDSD StockTraders AI - Update-30.06.pdf": {
                "chunks": ["Sóng lớn là trạng thái thị trường được xác nhận bởi hệ thống StockTraders AI."],
            },
            "Loi ich giao dich tai chan song lon.pdf": {
                "chunks": ["Giao dịch tại chân sóng lớn có một số lợi ích quan trọng."],
            },
        }

        result = rag.retrieve_best_book("sóng lớn là gì", top_k=1)

        self.assertEqual(result["doc_name"], "HDSD StockTraders AI - Update-30.06.pdf")

    def test_song_lon_benefit_question_can_select_benefit_book(self):
        rag = RAGStore.__new__(RAGStore)
        rag.book_docs = {
            "HDSD StockTraders AI - Update-30.06.pdf": {
                "chunks": ["Sóng lớn là trạng thái thị trường được xác nhận bởi hệ thống StockTraders AI."],
            },
            "Loi ich giao dich tai chan song lon.pdf": {
                "chunks": ["Lợi ích giao dịch tại chân sóng lớn là tiềm năng lợi nhuận cao."],
            },
        }

        result = rag.retrieve_best_book("lợi ích giao dịch tại chân sóng lớn", top_k=1)

        self.assertEqual(result["doc_name"], "Loi ich giao dich tai chan song lon.pdf")

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
    async def test_stock_analysis_question_selects_composite_rule(self):
        rag = RAGStore.__new__(RAGStore)
        rag.rule_docs = {
            "Cau hoi ve danh gia 4 key co phieu.txt": {},
            "Câu hỏi về giá của mã.txt": {},
            "Câu hỏi về mã, cổ phiếu, đạt chuẩn mã mạnh.txt": {},
        }

        selected = await rag.pick_doc("Phân tích cổ phiếu VCB hôm nay")

        self.assertEqual(selected, "Cau hoi ve danh gia 4 key co phieu.txt")

    async def test_score_question_selects_composite_rule(self):
        rag = RAGStore.__new__(RAGStore)
        rag.rule_docs = {
            "Cau hoi ve danh gia 4 key co phieu.txt": {},
            "Câu hỏi về giá của mã.txt": {},
            "Câu hỏi về sức mạnh dòng tiền, smdt ngành, mã.txt": {},
        }

        selected = await rag.pick_doc("Score của SSI hôm nay là bao nhiêu?")

        self.assertEqual(selected, "Cau hoi ve danh gia 4 key co phieu.txt")
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

    async def test_current_ticker_smdt_question_selects_smdt_rule_not_price(self):
        rag = RAGStore.__new__(RAGStore)
        rag.rule_docs = {
            "Cau hoi ve gia cua ma.txt": {},
            "Cau hoi ve suc manh dong tien, smdt nganh, ma.txt": {},
        }

        selected = await rag.pick_doc("SMDT GEX hien nay la bao nhieu?")

        self.assertEqual(selected, "Cau hoi ve suc manh dong tien, smdt nganh, ma.txt")

    def test_current_ticker_smdt_question_selects_single_ticker_chunk(self):
        rag = RAGStore.__new__(RAGStore)
        chunks = [
            'Guide SMDT nganh ngan hang tu [date] den nay. Goi getSMDTBranch theo tung thang.',
            'Guide SMDT suc manh dong tien co phieu [X] tu thang [month] den nay. Goi getSMDTTicker voi ma duoc hoi va date la tung thang.',
            'Guide Khi hoi: "SMDT [ma] la bao nhieu?". Goi getSMDTTicker voi ma va date duoc hoi kem %.',
        ]

        context = rag.build_context(
            "Cau hoi ve suc manh dong tien, smdt nganh, ma.txt",
            chunks,
            "SMDT GEX hien nay la bao nhieu?",
            max_chunks=1,
        )

        self.assertIn("SMDT [ma]", context["refs"])
        self.assertIn("getSMDTTicker", context["refs"])
        self.assertNotIn("tu thang", context["refs"])

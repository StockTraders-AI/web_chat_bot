import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.orchestrator import (  # noqa: E402
    Orchestrator,
    extract_branch_cashflow_items,
    format_branch_cashflow_answer,
    format_stock_cashflow_answer,
    is_branch_cashflow_query,
    is_stock_cashflow_query,
)


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def call(self, operation, args, **kwargs):
        self.calls.append((operation, args, kwargs))
        if operation == "getCashFlowTicker":
            return {
                "cashFlowTickers": [
                    {
                        "keyValue": "BSR",
                        "cashFlows": [
                            {"date": "2026-07-15", "content": "Tiền vào BSR", "value": 2}
                        ],
                    }
                ]
            }
        return {
            "cashFlowBranchs": [
                {
                    "date": "2026-07-20",
                    "cashFlowBranchDatas": [
                        {"content": "Tiền đang vào ngành ngân hàng", "value": 2}
                    ],
                }
            ]
        }


class BranchCashflowQueryTests(unittest.TestCase):
    def test_detects_branch_cashflow_query(self):
        self.assertTrue(is_branch_cashflow_query("dòng tiền ngành ngân hàng hiện nay thế nào"))
        self.assertFalse(is_branch_cashflow_query("SMDT ngành ngân hàng hiện nay là bao nhiêu"))

    def test_detects_stock_cashflow_query(self):
        self.assertTrue(is_stock_cashflow_query("dòng tiền BSR 15-7-2026 thế nào"))
        self.assertFalse(is_stock_cashflow_query("SMDT BSR 15-7-2026 thế nào"))

    def test_extract_branch_cashflow_items_handles_nested_payload(self):
        rows = extract_branch_cashflow_items(
            {
                "cashFlowBranchs": [
                    {
                        "date": "2026-07-20",
                        "cashFlowBranchDatas": [{"content": "Tiền vào"}],
                    }
                ]
            }
        )

        self.assertEqual(rows[0]["date"], "2026-07-20")
        self.assertEqual(rows[0]["content"], "Tiền vào")

    def test_extract_cash_ticker_datas_shape_from_live_api(self):
        rows = extract_branch_cashflow_items(
            [
                {
                    "date": "2026-07-20",
                    "cashTickerDatas": [
                        {
                            "content": "Tiếp tục đổ vào",
                            "percent": "0.00%",
                            "price": 0.0,
                            "ticker": "SSI",
                            "type": "HSX",
                        }
                    ],
                }
            ]
        )

        self.assertEqual(rows[0]["date"], "2026-07-20")
        self.assertEqual(rows[0]["ticker"], "SSI")
        self.assertEqual(rows[0]["content"], "Tiếp tục đổ vào")

    def test_answer_branch_cashflow_calls_cashflow_branch_with_path(self):
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.executor = FakeExecutor()

        question = "dòng tiền ngành ngân hàng hiện nay thế nào"
        answer = orchestrator._answer_branch_cashflow(question)

        self.assertEqual(
            answer,
            "Dòng tiền ngành ngân hàng phiên 20/07/2026: Tiền đang vào ngành ngân hàng",
        )
        self.assertEqual(
            orchestrator.executor.calls,
            [
                (
                    "getCashFlowBranch",
                    {"date": datetime.now().date().isoformat(), "path": "7-211-212-213-214-"},
                    {"user_text": question},
                )
            ],
        )

    def test_answer_stock_cashflow_calls_cashflow_ticker(self):
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.executor = FakeExecutor()

        question = "dòng tiền BSR 15-7-2026 thế nào"
        answer = orchestrator._answer_stock_cashflow(question)

        self.assertEqual(answer, "Dòng tiền BSR phiên 15/07/2026: Tiền vào BSR")
        self.assertEqual(
            orchestrator.executor.calls,
            [
                (
                    "getCashFlowTicker",
                    {"ticker": "BSR", "date": "2026-07-15"},
                    {"user_text": question},
                )
            ],
        )

    def test_format_stock_cashflow_answer_does_not_mention_smdt(self):
        answer = format_stock_cashflow_answer(
            "BSR",
            {"date": "2026-07-15", "content": "Tiền vào"},
            "2026-07-15",
        )

        self.assertNotIn("SMDT", answer)
        self.assertNotIn("sức mạnh dòng tiền", answer.lower())

    def test_format_branch_cashflow_answer_does_not_mention_tickers_or_smdt(self):
        answer = format_branch_cashflow_answer(
            "ngân hàng",
            {"date": "2026-07-20", "content": "Tiền vào"},
            "2026-07-20",
        )

        self.assertNotIn("SMDT", answer)
        self.assertNotIn("mã cổ phiếu", answer)


if __name__ == "__main__":
    unittest.main()
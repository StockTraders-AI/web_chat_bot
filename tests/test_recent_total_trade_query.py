import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.orchestrator import (  # noqa: E402
    Orchestrator,
    extract_recent_total_trade_request,
    format_recent_total_trade_answer,
    is_recent_total_trade_query,
)
from services.ticker_policy import invalid_api_ticker, sanitize_api_result  # noqa: E402


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def call(self, operation, args, **kwargs):
        self.calls.append((operation, args, kwargs))
        return [
            {
                "ticker": "VNINDEX",
                "date": "2026-07-17",
                "open": 1500.1,
                "high": 1512.5,
                "low": 1498.2,
                "close": 1510.3,
                "vol": 1000,
            },
            {
                "ticker": "VNINDEX",
                "date": "2026-07-16",
                "open": 1490,
                "high": 1502,
                "low": 1488,
                "close": 1500,
                "vol": 900,
            },
        ]


class RecentTotalTradeQueryTests(unittest.TestCase):
    def test_extracts_vnindex_last_dates_request(self):
        self.assertTrue(is_recent_total_trade_query("chỉ số VNINDEX trong 10 phiên gần nhất"))
        self.assertEqual(
            extract_recent_total_trade_request("chỉ số VNINDEX trong 10 phiên gần nhất"),
            {"ticker": "VNINDEX", "lastDates": 10},
        )

    def test_vnindex_is_allowed_for_total_trade_only(self):
        self.assertIsNone(invalid_api_ticker("getTotalTrade", {"ticker": "VNINDEX", "lastDates": 10}))
        self.assertEqual(invalid_api_ticker("getCashFlowTicker", {"ticker": "VNINDEX"}), "VNINDEX")
        self.assertEqual(
            sanitize_api_result("getTotalTrade", [{"ticker": "VNINDEX", "date": "2026-07-17", "close": 1510.3}]),
            [{"ticker": "VNINDEX", "date": "2026-07-17", "close": 1510.3}],
        )

    def test_answer_recent_total_trade_calls_total_trade_with_last_dates(self):
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.executor = FakeExecutor()

        answer = orchestrator._answer_recent_total_trade("chỉ số VNINDEX trong 10 phiên gần nhất")

        self.assertIn("VNINDEX trong 10 phiên gần nhất:", answer)
        self.assertIn("17/07/2026: close 1510.3, open 1500.1, high 1512.5, low 1498.2", answer)
        self.assertEqual(
            orchestrator.executor.calls,
            [("getTotalTrade", {"ticker": "VNINDEX", "lastDates": 10}, {"user_text": "chỉ số VNINDEX trong 10 phiên gần nhất"})],
        )

    def test_format_recent_total_trade_answer_lists_all_rows(self):
        text = format_recent_total_trade_answer(
            "SSI",
            [
                {"date": "2026-07-17", "open": 10, "high": 11, "low": 9, "close": 10.5},
                {"date": "2026-07-16", "open": 9, "high": 10, "low": 8, "close": 9.5},
            ],
            2,
        )

        self.assertEqual(len([line for line in text.splitlines() if line.startswith("- ")]), 2)


if __name__ == "__main__":
    unittest.main()

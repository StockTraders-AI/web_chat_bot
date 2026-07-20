import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.orchestrator import (  # noqa: E402
    Orchestrator,
    extract_recent_stock_wave_request,
    format_recent_stock_wave_answer,
    is_recent_stock_wave_query,
    recent_stock_wave_rows,
)


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def call(self, operation, args, **kwargs):
        self.calls.append((operation, args, kwargs))
        return {
            "name": "ALL",
            "waveDatas": [
                {
                    "date": "2026-07-17",
                    "buy": 10,
                    "sell": 4,
                    "waitbuy": 30,
                    "waitsell": 8,
                    "total": 52,
                    "reliability": 76.5,
                },
                {
                    "date": "2026-07-16",
                    "buy": 9,
                    "sell": 5,
                    "waitbuy": 28,
                    "waitsell": 7,
                    "total": 49,
                },
                {
                    "date": "2026-07-15",
                    "buy": 8,
                    "sell": 6,
                    "waitbuy": 26,
                    "waitsell": 6,
                    "total": 46,
                },
            ],
        }


class RecentStockWaveQueryTests(unittest.TestCase):
    def test_extracts_recent_stock_wave_request(self):
        self.assertTrue(is_recent_stock_wave_query("Số liệu dò sóng 20 phiên gần nhất"))
        self.assertEqual(
            extract_recent_stock_wave_request("Số liệu dò sóng 20 phiên gần nhất"),
            {"date": "2026", "lastDates": 20},
        )

    def test_recent_stock_wave_query_excludes_chan_song(self):
        self.assertFalse(is_recent_stock_wave_query("chân sóng 20 phiên gần nhất"))

    def test_recent_stock_wave_rows_sorts_and_limits(self):
        rows = recent_stock_wave_rows(
            {
                "waveDatas": [
                    {"date": "2026-07-15", "waitbuy": 1},
                    {"date": "2026-07-17", "waitbuy": 3},
                    {"date": "2026-07-16", "waitbuy": 2},
                ]
            },
            2,
        )

        self.assertEqual([row["date"] for row in rows], ["2026-07-17", "2026-07-16"])

    def test_answer_recent_stock_wave_calls_stock_wave_by_year(self):
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.executor = FakeExecutor()

        answer = orchestrator._answer_recent_stock_wave("Số liệu dò sóng 20 phiên gần nhất")

        self.assertIn("Số liệu dò sóng 20 phiên gần nhất:", answer)
        self.assertIn("17/07/2026: mua 10, bán 4, chờ mua 30, chờ bán 8, tổng 52, độ tin cậy 76.5%", answer)
        self.assertEqual(
            orchestrator.executor.calls,
            [("getStockWave", {"date": "2026"}, {"user_text": "Số liệu dò sóng 20 phiên gần nhất"})],
        )

    def test_format_recent_stock_wave_answer_lists_all_rows(self):
        text = format_recent_stock_wave_answer(
            [
                {"date": "2026-07-17", "buy": 10, "sell": 4, "waitbuy": 30, "waitsell": 8, "total": 52},
                {"date": "2026-07-16", "buy": 9, "sell": 5, "waitbuy": 28, "waitsell": 7, "total": 49},
            ],
            2,
        )

        self.assertEqual(len([line for line in text.splitlines() if line.startswith("- ")]), 2)


if __name__ == "__main__":
    unittest.main()

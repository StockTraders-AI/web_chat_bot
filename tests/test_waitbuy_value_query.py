import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.orchestrator import (  # noqa: E402
    Orchestrator,
    _normalize_waitbuy_lookup_date,
    extract_stock_wave_metric,
    extract_stock_wave_rows,
    format_stock_wave_value_answer,
    is_stock_wave_value_query,
    is_waitbuy_value_query,
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
                    "date": "2026-03-24",
                    "buy": 10,
                    "sell": 5,
                    "total": 100,
                    "waitbuy": 42,
                    "waitsell": 7,
                    "reliability": 76.5,
                }
            ],
        }


class WaitbuyValueQueryTests(unittest.TestCase):
    def test_waitbuy_session_date_is_direct_value_query(self):
        self.assertTrue(is_waitbuy_value_query("chờ mua phiên 24/3"))
        self.assertEqual(
            _normalize_waitbuy_lookup_date("chờ mua phiên 24/3"),
            "2026-03-24",
        )

    def test_waitbuy_explanation_stays_explanation_query(self):
        self.assertFalse(is_waitbuy_value_query("giải thích chờ mua tăng mạnh"))

    def test_stock_wave_value_query_uses_metric_registry(self):
        self.assertEqual(extract_stock_wave_metric("chờ bán phiên 24/3 bao nhiêu"), "waitsell")
        self.assertTrue(is_stock_wave_value_query("chờ bán phiên 24/3 bao nhiêu"))
        self.assertFalse(is_waitbuy_value_query("chờ bán phiên 24/3 bao nhiêu"))
        self.assertFalse(is_stock_wave_value_query("Chờ mua là gì?"))

    def test_extract_stock_wave_rows_handles_wrapped_wave_datas(self):
        rows = extract_stock_wave_rows({"name": "ALL", "waveDatas": [{"date": "2026-03-24", "waitbuy": 42}]})
        self.assertEqual(rows, [{"date": "2026-03-24", "waitbuy": 42}])

    def test_answer_waitbuy_value_calls_get_stock_wave_with_full_date(self):
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.executor = FakeExecutor()

        answer = orchestrator._answer_waitbuy_value("chờ mua phiên 24/3")

        self.assertEqual(answer, "Phiên 24/03/2026 có 42 cổ phiếu chờ mua.")
        self.assertEqual(
            orchestrator.executor.calls,
            [("getStockWave", {"date": "2026-03-24"}, {"user_text": "chờ mua phiên 24/3"})],
        )

    def test_answer_stock_wave_value_supports_other_registered_metrics(self):
        orchestrator = Orchestrator.__new__(Orchestrator)
        orchestrator.executor = FakeExecutor()

        answer = orchestrator._answer_stock_wave_value("chờ bán phiên 24/3 bao nhiêu")

        self.assertEqual(answer, "Phiên 24/03/2026 có 7 cổ phiếu chờ bán.")
        self.assertEqual(
            orchestrator.executor.calls,
            [("getStockWave", {"date": "2026-03-24"}, {"user_text": "chờ bán phiên 24/3 bao nhiêu"})],
        )

    def test_format_stock_wave_value_handles_percent_metric(self):
        self.assertEqual(
            format_stock_wave_value_answer({"date": "2026-03-24", "reliability": 76.5}, "2026-03-24", "reliability"),
            "Phiên 24/03/2026 có độ tin cậy 76.5%.",
        )


if __name__ == "__main__":
    unittest.main()

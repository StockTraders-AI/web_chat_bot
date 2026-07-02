import unittest
from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.stock_4key_evaluator import (
    CashFlowPoint,
    PricePoint,
    SmdtPoint,
    evaluate_four_key_from_records,
    evaluate_stock_4key,
)


class Stock4KeyEvaluatorTests(unittest.TestCase):
    def test_single_evaluation_with_composite(self):
        ticker_points = [
            SmdtPoint("2026-06-26", 50),
            SmdtPoint("2026-06-29", 55),
            SmdtPoint("2026-06-30", 61),
            SmdtPoint("2026-07-01", 70),
        ]
        branch_points = [
            SmdtPoint("2026-06-26", 45),
            SmdtPoint("2026-06-29", 47),
            SmdtPoint("2026-06-30", 48),
            SmdtPoint("2026-07-01", 52),
        ]
        price_points = [
            PricePoint("2026-06-26", 100),
            PricePoint("2026-06-29", 99),
            PricePoint("2026-06-30", 99),
            PricePoint("2026-07-01", 99),
        ]

        result = evaluate_four_key_from_records(
            ticker="SSI",
            branch_name="Moi gioi chung khoan",
            ticker_smdt=ticker_points,
            branch_smdt=branch_points,
            requested_date="2026-07-01",
            price_points=price_points,
            cashflow_points=[CashFlowPoint("2026-07-01", 1)],
        )

        self.assertEqual(result["group_4key"], "Dung song - Dung nganh")
        self.assertEqual(result["ticker_momentum"], 20)
        self.assertEqual(result["branch_momentum"], 7)
        self.assertIn("composite", result)
        self.assertTrue(result["composite"]["co_phan_ky"])

    def test_api_adapter_single(self):
        seen = []

        def api_call(operation, args):
            seen.append((operation, args))
            if operation == "getSMDTLastN" and args.get("ticker") == "SSI":
                return {"type": "ticker", "ticker": "SSI", "smdts": [
                    {"date": "2026-06-26", "smdt": 50},
                    {"date": "2026-06-29", "smdt": 55},
                    {"date": "2026-06-30", "smdt": 61},
                    {"date": "2026-07-01", "smdt": 70},
                ]}
            if operation == "getSMDTLastN" and args.get("path"):
                return {"type": "branch", "keyName": "Moi gioi chung khoan", "path": args.get("path"), "smdts": [
                    {"date": "2026-06-26", "smdt": 45},
                    {"date": "2026-06-29", "smdt": 47},
                    {"date": "2026-06-30", "smdt": 48},
                    {"date": "2026-07-01", "smdt": 52},
                ]}
            if operation == "getTotalTradeWithSMDT":
                self.fail("4-key adapter must not fetch price with getTotalTradeWithSMDT")
            if operation == "getTotalTrade":
                return [
                    {"date": "2026-06-26", "close": 100},
                    {"date": "2026-06-29", "close": 100},
                    {"date": "2026-06-30", "close": 101},
                    {"date": "2026-07-01", "close": 102},
                ]
            if operation == "getCashFlowTicker":
                return {"cashFlowTickers": [{"cashFlows": [{"date": "2026-07-01", "value": 1}]}]}
            return {}

        result = evaluate_stock_4key(api_call, {"ticker": "SSI", "date": "2026-07-01"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["ticker"], "SSI")
        self.assertEqual(result["date"], "2026-07-01")
        smdt_calls = [(operation, args) for operation, args in seen if operation == "getSMDTLastN"]
        self.assertEqual(len(smdt_calls), 2)
        self.assertTrue(all(args["n"] == 45 for _, args in smdt_calls))
        price_calls = [(operation, args) for operation, args in seen if operation == "getTotalTrade"]
        self.assertEqual(price_calls, [("getTotalTrade", {"ticker": "SSI", "lastDates": 45})])


    def test_today_adapter_uses_realtime_price_and_cashflow_content(self):
        target = date.today()
        dates = [(target - timedelta(days=offset)).isoformat() for offset in (4, 3, 2, 0)]
        seen = []

        def api_call(operation, args):
            seen.append((operation, args))
            if operation == "getSMDTLastN" and args.get("ticker") == "SSI":
                return {"type": "ticker", "ticker": "SSI", "smdts": [
                    {"date": dates[0], "smdt": 50},
                    {"date": dates[1], "smdt": 55},
                    {"date": dates[2], "smdt": 61},
                    {"date": dates[3], "smdt": 70},
                ]}
            if operation == "getSMDTLastN" and args.get("path"):
                return {"type": "branch", "keyName": "Moi gioi chung khoan", "path": args.get("path"), "smdts": [
                    {"date": dates[0], "smdt": 45},
                    {"date": dates[1], "smdt": 47},
                    {"date": dates[2], "smdt": 48},
                    {"date": dates[3], "smdt": 52},
                ]}
            if operation == "getTotalTrade":
                return [
                    {"date": dates[0], "close": 100},
                    {"date": dates[1], "close": 100},
                    {"date": dates[2], "close": 101},
                ]
            if operation == "getTotalTradeReal":
                return [{"date": dates[3], "close": 102, "ticker": "SSI"}]
            if operation == "getCashFlowTicker":
                return {"cashFlowTickers": [{"cashFlows": [{"date": dates[3], "content": "Tiếp tục thoát ra"}]}]}
            return {}

        result = evaluate_stock_4key(api_call, {"ticker": "SSI", "date": dates[3]})
        self.assertTrue(result["ok"])
        self.assertIn(("getTotalTradeReal", {"ticker": "SSI"}), seen)
        self.assertIn("gia_dong_luong", result["composite"]["breakdown"])
        self.assertEqual(result["composite"]["breakdown"]["dong_tien"], 0.0)
if __name__ == "__main__":
    unittest.main()

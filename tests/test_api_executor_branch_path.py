import unittest
from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.api_executor import APIExecutor


class FakeResponse:
    ok = True
    status_code = 200

    def __init__(self, payload=None):
        self.payload = [] if payload is None else payload
        self.text = "[]"

    def json(self):
        return self.payload


class FakeRegistry:
    server_url = "https://example.test"
    operations = {
        "getSMDTBranch": {
            "path": "/service/data/getSMDTBranch",
            "method": "POST",
        },
        "getSMDTTicker": {
            "path": "/service/data/getSMDTTicker",
            "method": "POST",
        },
        "getCashFlowTicker": {
            "path": "/service/data/getCashFlowTicker",
            "method": "POST",
        },
    }


class APIExecutorBranchPathTests(unittest.TestCase):
    def test_get_smdt_branch_normalizes_name_to_path_and_keeps_date(self):
        executor = APIExecutor(FakeRegistry())
        captured = {}

        def fake_execute(url, method, args):
            captured.update(args)
            return FakeResponse()

        executor._execute_with_retry = fake_execute
        executor.call(
            "getSMDTBranch",
            {"keyName": "Chứng khoán", "date": "2025-04-09"},
        )

        self.assertEqual(captured["path"], "9-246-250-257-271-")
        self.assertEqual(captured["date"], "2025-04-09")
        self.assertNotIn("keyName", captured)

    def test_get_smdt_branch_keeps_explicit_path(self):
        executor = APIExecutor(FakeRegistry())
        captured = {}

        def fake_execute(url, method, args):
            captured.update(args)
            return FakeResponse()

        executor._execute_with_retry = fake_execute
        executor.call(
            "getSMDTBranch",
            {"path": "9-246-250-257-271-", "date": "2025-04-09"},
        )

        self.assertEqual(captured["path"], "9-246-250-257-271-")
        self.assertEqual(captured["date"], "2025-04-09")

    def test_current_day_empty_result_retries_previous_dates(self):
        executor = APIExecutor(FakeRegistry())
        today = date.today()
        yesterday = today - timedelta(days=1)
        calls = []

        def fake_execute(url, method, args):
            calls.append(dict(args))
            if args.get("date") == yesterday.isoformat():
                return FakeResponse([{"date": yesterday.isoformat(), "smdt": 91.5, "ticker": "GEX"}])
            return FakeResponse([])

        executor._execute_with_retry = fake_execute
        result = executor.call(
            "getSMDTTicker",
            {"ticker": "GEX", "date": today.isoformat()},
            user_text="SMDT cua GEX",
        )

        self.assertEqual(calls[0]["date"], today.isoformat())
        self.assertEqual(calls[1]["date"], yesterday.isoformat())
        self.assertEqual(result[0]["date"], yesterday.isoformat())

    def test_explicit_calendar_date_does_not_retry_previous_dates(self):
        executor = APIExecutor(FakeRegistry())
        today = date.today()
        calls = []

        def fake_execute(url, method, args):
            calls.append(dict(args))
            return FakeResponse([])

        executor._execute_with_retry = fake_execute
        result = executor.call(
            "getSMDTTicker",
            {"ticker": "GEX", "date": today.isoformat()},
            user_text=f"SMDT GEX ngay {today.day}",
        )

        self.assertEqual(result, [])
        self.assertEqual(len(calls), 1)

    def test_implicit_current_question_coerces_hallucinated_month_to_today(self):
        executor = APIExecutor(FakeRegistry())
        today = date.today()
        yesterday = today - timedelta(days=1)
        calls = []

        def fake_execute(url, method, args):
            calls.append(dict(args))
            if args.get("date") == yesterday.isoformat():
                return FakeResponse([{"date": yesterday.isoformat(), "smdt": 88.0, "ticker": "GEX"}])
            return FakeResponse([])

        executor._execute_with_retry = fake_execute
        result = executor.call(
            "getSMDTTicker",
            {"keyValue": "GEX", "date": "2023-10"},
            user_text="SMDT GEX hien nay la bao nhieu?",
        )

        self.assertEqual(calls[0]["date"], today.isoformat())
        self.assertEqual(calls[1]["date"], yesterday.isoformat())
        self.assertEqual(result[0]["date"], yesterday.isoformat())

    def test_explicit_month_question_keeps_requested_month(self):
        executor = APIExecutor(FakeRegistry())
        calls = []

        def fake_execute(url, method, args):
            calls.append(dict(args))
            return FakeResponse([])

        executor._execute_with_retry = fake_execute
        result = executor.call(
            "getSMDTTicker",
            {"keyValue": "GEX", "date": "2023-10"},
            user_text="SMDT GEX thang 10 nam 2023",
        )

        self.assertEqual(result, [])
        self.assertEqual(calls[0]["date"], "2023-10")
        self.assertEqual(len(calls), 1)
    def test_cashflow_today_empty_retries_without_date_once(self):
        executor = APIExecutor(FakeRegistry())
        today = date.today().isoformat()
        calls = []

        def fake_execute(url, method, args):
            calls.append(dict(args))
            if "date" not in args:
                return FakeResponse({"cashFlowTickers": [{"date": today, "ticker": "NVL", "content": "Đang đổ vào"}]})
            return FakeResponse({"cashFlowTickers": []})

        executor._execute_with_retry = fake_execute
        result = executor.call(
            "getCashFlowTicker",
            {"ticker": "NVL", "date": today},
            user_text="Dòng tiền NVL hiện nay thế nào?",
        )

        self.assertEqual(calls[0], {"ticker": "NVL", "date": today})
        self.assertEqual(calls[1], {"ticker": "NVL"})
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["cashFlowTickers"][0]["ticker"], "NVL")


if __name__ == "__main__":
    unittest.main()

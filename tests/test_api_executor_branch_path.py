import unittest

from services.api_executor import APIExecutor


class FakeResponse:
    ok = True
    status_code = 200
    text = "[]"

    def json(self):
        return []


class FakeRegistry:
    server_url = "https://example.test"
    operations = {
        "getSMDTBranch": {
            "path": "/service/data/getSMDTBranch",
            "method": "POST",
        }
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


if __name__ == "__main__":
    unittest.main()
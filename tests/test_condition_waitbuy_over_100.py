import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.condition_engine import (  # noqa: E402
    resolve_condition_key,
    resolve_template_support,
    run_condition,
)


async def fake_stock_wave_api(endpoint, params=None):
    return {
        "waveDatas": [
            {
                "date": params["date"],
                "waitbuy": 101,
            }
        ]
    }


class WaitbuyOver100ConditionTests(unittest.IsolatedAsyncioTestCase):
    def test_resolves_condition_12_text_to_waitbuy_over_100(self):
        text = "S\u00f3ng th\u1ecb tr\u01b0\u1eddng Ch\u1edd mua t\u0103ng m\u1ea1nh Ch\u1edd mua > 100"
        self.assertEqual(resolve_condition_key(text), "waitbuy_over_100")

    def test_existing_waitbuy_over_200_still_resolves(self):
        self.assertEqual(resolve_condition_key("Cho mua > 200"), "waitbuy_over_200")

    def test_template_support_marks_waitbuy_over_100_supported(self):
        template = {
            "type": "song_thi_truong",
            "name": "Ch\u1edd mua t\u0103ng m\u1ea1nh",
            "condition_logic": "Ch\u1edd mua > 100",
        }

        support = resolve_template_support(template)

        self.assertEqual(support["resolved_condition_key"], "waitbuy_over_100")
        self.assertEqual(support["support_status"], "supported")

    async def test_run_condition_waitbuy_over_100_matches_when_latest_waitbuy_above_100(self):
        with patch("core.condition_engine.post_data_api", fake_stock_wave_api):
            result = await run_condition(
                template_id=12,
                context={
                    "condition_key": "Ch\u1edd mua > 100",
                    "date": "2026-07-22",
                },
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["matched"])
        self.assertEqual(result["condition_key"], "waitbuy_over_100")
        self.assertEqual(result["data"]["waitbuy"], 101.0)


if __name__ == "__main__":
    unittest.main()

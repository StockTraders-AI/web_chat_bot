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
from core.realtime_wave import clear_wave_cache, update_wave_payload  # noqa: E402


class WaitbuyOver100ConditionTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        clear_wave_cache()

    def test_resolves_condition_12_text_to_waitbuy_over_100(self):
        text = "Sóng thị trường Chờ mua tăng mạnh Chờ mua > 100"
        self.assertEqual(resolve_condition_key(text), "waitbuy_over_100")

    def test_existing_waitbuy_over_200_still_resolves(self):
        self.assertEqual(resolve_condition_key("Cho mua > 200"), "waitbuy_over_200")

    def test_template_support_marks_waitbuy_over_100_supported(self):
        template = {
            "type": "song_thi_truong",
            "name": "Chờ mua tăng mạnh",
            "condition_logic": "Chờ mua > 100",
        }

        support = resolve_template_support(template)

        self.assertEqual(support["resolved_condition_key"], "waitbuy_over_100")
        self.assertEqual(support["support_status"], "supported")

    async def test_run_condition_waitbuy_over_100_uses_realtime_wave_cache(self):
        update_wave_payload({
            "channel": "wave",
            "data": {
                "waveDatas": [
                    {
                        "date": "2026-07-22",
                        "waitbuy": 101,
                    }
                ]
            },
            "sentAt": "2026-07-22T03:00:00.000Z",
        })

        with patch("core.condition_engine.post_data_api") as post_data_api:
            result = await run_condition(
                template_id=12,
                context={
                    "condition_key": "Chờ mua > 100",
                    "date": "2026-07-22",
                },
            )

        post_data_api.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertTrue(result["matched"])
        self.assertEqual(result["condition_key"], "waitbuy_over_100")
        self.assertEqual(result["data"]["waitbuy"], 101.0)
        self.assertEqual(result["data"]["source"], "realtime_wave")

    async def test_run_condition_waitbuy_over_100_does_not_fallback_to_stock_wave_api(self):
        with patch("core.condition_engine.post_data_api") as post_data_api:
            result = await run_condition(
                template_id=12,
                context={
                    "condition_key": "Chờ mua > 100",
                    "date": "2026-07-22",
                },
            )

        post_data_api.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertFalse(result["matched"])
        self.assertEqual(result["error"]["type"], "realtime_wave_unavailable")


if __name__ == "__main__":
    unittest.main()

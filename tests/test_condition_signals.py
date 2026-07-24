import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.memory import MemoryStore  # noqa: E402


class ConditionSignalStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.store = MemoryStore(self.db_path)
        await self.store.init()

    async def asyncTearDown(self):
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass

    async def test_upsert_and_read_latest_condition_signal(self):
        await self.store.upsert_condition_signal(
            flow_id=12,
            flow_name="Cho mua tang manh",
            condition_keys=["waitbuy_over_100"],
            signal_key="waitbuy_over_100",
            title="Cho mua tang manh",
            message="Lan 1",
            condition_results=[{"matched": True}],
            check_date="2026-07-22",
            source="realtime_wave",
            delivery_key="12:2026-07-22",
        )
        await self.store.upsert_condition_signal(
            flow_id=12,
            flow_name="Cho mua tang manh",
            condition_keys=["waitbuy_over_100"],
            signal_key="waitbuy_over_100",
            title="Cho mua tang manh",
            message="Lan 2",
            condition_results=[{"matched": True, "value": 101}],
            recommendation="Khuyen nghi 2",
            check_date="2026-07-22",
            source="realtime_wave",
            delivery_key="12:2026-07-22",
        )

        latest = await self.store.get_latest_condition_signal(signal_key="waitbuy_over_100")
        signals = await self.store.list_condition_signals(signal_key="waitbuy_over_100")

        self.assertEqual(len(signals), 1)
        self.assertEqual(latest["flow_id"], 12)
        self.assertEqual(latest["message"], "Lan 2")
        self.assertEqual(latest["recommendation"], "Khuyen nghi 2")
        self.assertEqual(latest["condition_keys"], ["waitbuy_over_100"])
        self.assertEqual(latest["condition_results"][0]["value"], 101)

    async def test_signal_state_only_publishes_on_false_to_true_transition(self):
        first = await self.store.update_condition_signal_state(
            flow_id=12,
            signal_key="waitbuy_over_100",
            matched=True,
            check_date="2026-07-22",
        )
        second = await self.store.update_condition_signal_state(
            flow_id=12,
            signal_key="waitbuy_over_100",
            matched=True,
            check_date="2026-07-22",
        )
        reset = await self.store.update_condition_signal_state(
            flow_id=12,
            signal_key="waitbuy_over_100",
            matched=False,
            check_date="2026-07-22",
        )
        third = await self.store.update_condition_signal_state(
            flow_id=12,
            signal_key="waitbuy_over_100",
            matched=True,
            check_date="2026-07-22",
        )

        self.assertTrue(first["should_publish"])
        self.assertEqual(first["transition_count"], 1)
        self.assertFalse(second["should_publish"])
        self.assertEqual(second["transition_count"], 1)
        self.assertFalse(reset["should_publish"])
        self.assertFalse(reset["matched"])
        self.assertTrue(third["should_publish"])
        self.assertEqual(third["transition_count"], 2)
        self.assertNotEqual(first["delivery_key"], third["delivery_key"])

        state = await self.store.get_condition_signal_state(
            flow_id=12,
            signal_key="waitbuy_over_100",
        )
        self.assertTrue(state["matched"])
        self.assertEqual(state["transition_count"], 2)

    async def test_condition_flow_signal_card_copy_fields_are_persisted(self):
        flow_id = await self.store.create_condition_flow(
            name="Cho mua tang",
            expression="12",
            prompt_template="prompt",
            trigger_prompt="response prompt",
            trigger_title="custom title",
            trigger_recommendation="custom recommendation",
        )

        flow = await self.store.get_condition_flow(flow_id)
        self.assertEqual(flow["trigger_title"], "custom title")
        self.assertEqual(flow["trigger_recommendation"], "custom recommendation")

        await self.store.update_condition_flow_trigger_prompt(
            flow_id=flow_id,
            trigger_prompt="updated response",
            trigger_title="updated title",
            trigger_recommendation="updated recommendation",
        )

        updated = await self.store.get_condition_flow(flow_id)
        self.assertEqual(updated["trigger_prompt"], "updated response")
        self.assertEqual(updated["trigger_title"], "updated title")
        self.assertEqual(updated["trigger_recommendation"], "updated recommendation")


if __name__ == "__main__":
    unittest.main()

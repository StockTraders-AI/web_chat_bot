import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.context_resolver import resolve_conversation_context


class ContextResolverTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 10, 11, 0, 0)

    def test_current_complete_does_not_use_history(self):
        result = resolve_conversation_context(
            "SMDT HPG ngày 28/7 bao nhiêu?",
            conversation_state={"intent": "metric_lookup", "topic": "stock_metric", "metric": "SMDT", "entities": ["SSI"]},
            now=self.now,
        )

        self.assertFalse(result["used_history"])
        self.assertEqual(result["used_turns"], 0)
        self.assertEqual(result["resolved_query"], "SMDT HPG ngày 28/07/2026 bao nhiêu?")
        self.assertEqual(result["next_state"]["entities"], ["HPG"])

    def test_entity_followup_inherits_missing_fields_from_state(self):
        result = resolve_conversation_context(
            "còn SSI?",
            conversation_state={
                "intent": "metric_lookup",
                "topic": "stock_metric",
                "metric": "SMDT",
                "entities": ["HPG"],
                "time_context": "2026-07-28",
            },
            now=self.now,
        )

        self.assertTrue(result["used_history"])
        self.assertEqual(result["history_source"], "state")
        self.assertEqual(result["resolved_query"], "SMDT SSI ngày 28/07/2026 bao nhiêu?")
        self.assertIn("metric", result["inherited_fields"])
        self.assertIn("entities", result["overridden_fields"])

    def test_next_day_followup_uses_state_date(self):
        result = resolve_conversation_context(
            "ngày hôm sau thì sao?",
            conversation_state={
                "intent": "metric_lookup",
                "topic": "stock_metric",
                "metric": "SMDT",
                "entities": ["SSI"],
                "time_context": "2026-07-28",
            },
            now=self.now,
        )

        self.assertEqual(result["resolved_query"], "SMDT SSI ngày 29/07/2026 bao nhiêu?")
        self.assertEqual(result["next_state"]["time_context"], "2026-07-29")

    def test_new_complete_topic_replaces_old_state(self):
        result = resolve_conversation_context(
            "Dòng tiền ngân hàng hôm nay thế nào?",
            conversation_state={
                "intent": "metric_lookup",
                "topic": "stock_metric",
                "metric": "SMDT",
                "entities": ["SSI"],
                "time_context": "2026-07-28",
            },
            now=self.now,
        )

        self.assertFalse(result["used_history"])
        self.assertEqual(result["next_state"]["topic"], "cashflow")
        self.assertNotEqual(result["next_state"].get("metric"), "SMDT")

    def test_date_only_followup_overrides_time_and_inherits_rest(self):
        result = resolve_conversation_context(
            "ngày 30/7",
            conversation_state={
                "intent": "metric_lookup",
                "topic": "stock_metric",
                "metric": "SMDT",
                "entities": ["SSI"],
                "time_context": "2026-07-28",
            },
            now=self.now,
        )

        self.assertEqual(result["resolved_query"], "SMDT SSI ngày 30/07/2026 bao nhiêu?")
        self.assertIn("entities", result["inherited_fields"])
        self.assertIn("time", result["overridden_fields"])


    def test_market_wave_date_followup_inherits_metric_without_entity(self):
        cases = [
            ("chờ mua ngày 22-7 bao nhiêu", "waitbuy", "chờ mua ngày 28/07/2026 bao nhiêu?"),
            ("chờ bán phiên 22/7 bao nhiêu", "waitsell", "chờ bán ngày 28/07/2026 bao nhiêu?"),
            ("độ tin cậy ngày 22/7 bao nhiêu", "reliability", "độ tin cậy ngày 28/07/2026 bao nhiêu?"),
        ]

        for first_query, metric, expected in cases:
            with self.subTest(metric=metric):
                first = resolve_conversation_context(first_query, now=self.now)
                self.assertFalse(first["need_more_context"])
                self.assertEqual(first["next_state"]["topic"], "market_wave")
                self.assertEqual(first["next_state"]["metric"], metric)

                second = resolve_conversation_context(
                    "28/7 bao nhiêu",
                    conversation_state=first["next_state"],
                    now=self.now,
                )

                self.assertTrue(second["used_history"])
                self.assertEqual(second["resolved_query"], expected)

    def test_market_wave_definition_is_not_saved_as_metric_lookup(self):
        result = resolve_conversation_context("Chờ mua là gì?", now=self.now)

        self.assertFalse(result["need_more_context"])
        self.assertNotEqual(result["next_state"].get("topic"), "market_wave")


if __name__ == "__main__":
    unittest.main()

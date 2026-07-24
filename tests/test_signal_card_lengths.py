import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from main import (  # noqa: E402
    count_visible_signal_chars,
    fit_signal_text_by_visible_chars,
    parse_signal_response_ai_content,
)


class SignalCardLengthTests(unittest.TestCase):
    def test_fit_keeps_short_text_without_padding_by_default(self):
        title = fit_signal_text_by_visible_chars("Ch\u1edd mua t\u0103ng", target_visible_chars=60)
        response = fit_signal_text_by_visible_chars(
            "Ch\u1edd mua hi\u1ec7n t\u1ea1i \u1edf m\u1ee9c 126",
            target_visible_chars=200,
        )
        recommendation = fit_signal_text_by_visible_chars(
            "N\u00ean quan s\u00e1t k\u1ef9",
            target_visible_chars=100,
        )

        self.assertLess(count_visible_signal_chars(title), 60)
        self.assertLess(count_visible_signal_chars(response), 200)
        self.assertLess(count_visible_signal_chars(recommendation), 100)

    def test_fit_truncates_long_text_to_visible_limit(self):
        text = "abc def ghi jkl mno pqr stu vwx yz"
        fitted = fit_signal_text_by_visible_chars(text, target_visible_chars=10)

        self.assertEqual(count_visible_signal_chars(fitted), 10)

    def test_response_parse_does_not_pad_short_ai_text(self):
        response = parse_signal_response_ai_content(
            '{"response":"Waitbuy is 126 and market cash flow is improving."}',
            "fallback",
        )

        self.assertIn("126", response)
        self.assertLess(count_visible_signal_chars(response), 200)
        self.assertNotIn(" y ", f" {response} ".lower())


if __name__ == "__main__":
    unittest.main()

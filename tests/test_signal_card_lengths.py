import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from main import count_visible_signal_chars, fit_signal_text_by_visible_chars  # noqa: E402


class SignalCardLengthTests(unittest.TestCase):
    def test_fit_extends_short_text_to_exact_visible_length(self):
        title = fit_signal_text_by_visible_chars("Ch\u1edd mua t\u0103ng", target_visible_chars=30)
        response = fit_signal_text_by_visible_chars(
            "Ch\u1edd mua hi\u1ec7n t\u1ea1i \u1edf m\u1ee9c 126",
            target_visible_chars=105,
        )
        recommendation = fit_signal_text_by_visible_chars(
            "N\u00ean quan s\u00e1t k\u1ef9",
            target_visible_chars=50,
        )

        self.assertEqual(count_visible_signal_chars(title), 30)
        self.assertEqual(count_visible_signal_chars(response), 105)
        self.assertEqual(count_visible_signal_chars(recommendation), 50)

    def test_fit_truncates_long_text_to_exact_visible_length(self):
        text = "abc def ghi jkl mno pqr stu vwx yz"
        fitted = fit_signal_text_by_visible_chars(text, target_visible_chars=10)

        self.assertEqual(count_visible_signal_chars(fitted), 10)


if __name__ == "__main__":
    unittest.main()

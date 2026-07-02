import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.ticker_policy import sanitize_response_text


class TickerPolicySanitizeTests(unittest.TestCase):
    def test_keeps_4key_recommendation_line_with_mua_keyword(self):
        text = (
            '1. Diem Composite: VND co diem tong hop la 28.8.\n'
            '2. Nhom 4 Key: "Dung song - Dung nganh", khuyen nghi "MUA - tin hieu thuan ca ma va nganh".\n'
            '3. SMDT va Dong luc: VND tang.'
        )

        cleaned = sanitize_response_text(text)

        self.assertIn('2. Nhom 4 Key', cleaned)
        self.assertIn('MUA - tin hieu', cleaned)
        self.assertIn('3. SMDT va Dong luc', cleaned)

    def test_keeps_4key_recommendation_line_with_other_recommendation_keywords(self):
        for keyword in ("CAN NHAC", "THEO DOI", "TRANH"):
            with self.subTest(keyword=keyword):
                text = f'1. Nhom 4 Key: "X", khuyen nghi "{keyword} - noi dung".'
                self.assertIn(keyword, sanitize_response_text(text))


if __name__ == "__main__":
    unittest.main()
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
        self.assertIn('MUA - t\u00edn hi\u1ec7u', cleaned)
        self.assertIn('3. SMDT va Dong luc', cleaned)

    def test_keeps_4key_recommendation_line_with_other_recommendation_keywords(self):
        for keyword in ("CAN NHAC", "THEO DOI", "TRANH"):
            with self.subTest(keyword=keyword):
                text = f'1. Nhom 4 Key: "X", khuyen nghi "{keyword} - noi dung".'
                self.assertIn(keyword, sanitize_response_text(text))

    def test_normalizes_four_key_labels_to_vietnamese_accents(self):
        text = 'BVS thu\u1ed9c nh\u00f3m 4-key "D\u00f9ng s\u00f3ng-D\u00f9ng ng\u00e0nh" (dd).'

        cleaned = sanitize_response_text(text)

        self.assertEqual(cleaned, 'BVS thu\u1ed9c nh\u00f3m 4 Key "\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh" (dd).')
        self.assertNotIn('D\u00f9ng s\u00f3ng', cleaned)
        self.assertNotIn('4-key', cleaned)

    def test_normalizes_4key_notes_to_vietnamese_accents(self):
        text = '- Thieu du lieu dong tien, tinh trung lap 50 diem.'

        cleaned = sanitize_response_text(text)

        self.assertEqual(cleaned, 'Thi\u1ebfu d\u1eef li\u1ec7u d\u00f2ng ti\u1ec1n cho ng\u00e0y n\u00e0y -> t\u00ednh nh\u01b0 trung l\u1eadp (50 \u0111i\u1ec3m).')
        self.assertNotIn('Thieu du lieu', cleaned)
    def test_normalizes_llm_paraphrased_4key_notes_to_vietnamese_accents(self):
        text = '- Phat hien phan ky: SMDT tang 42.1% nhung gia 3 phien la -5.2%.\n- Thieu du lieu dong tien, tinh trung lap 50 diem.'

        cleaned = sanitize_response_text(text)

        self.assertIn('Ph\u00e1t hi\u1ec7n ph\u00e2n k\u1ef3: SMDT t\u0103ng 42.1% nh\u01b0ng gi\u00e1 3 phi\u00ean l\u00e0 -5.2%.', cleaned)
        self.assertIn('Thi\u1ebfu d\u1eef li\u1ec7u d\u00f2ng ti\u1ec1n cho ng\u00e0y n\u00e0y -> t\u00ednh nh\u01b0 trung l\u1eadp (50 \u0111i\u1ec3m).', cleaned)
        self.assertNotIn('Phat hien', cleaned)
        self.assertNotIn('Thieu du lieu', cleaned)


if __name__ == "__main__":
    unittest.main()

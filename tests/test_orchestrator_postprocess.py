import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.orchestrator import ensure_stock_4key_section, format_stock_4key_answer, latest_stock_4key_payload, should_force_rules, is_stock_related


class OrchestratorPostprocessTests(unittest.TestCase):
    def test_inserts_missing_4key_section_and_renumbers(self):
        final_text = (
            'Phan tich co phieu CTS ngay 2 thang 7 nam 2026 nhu sau:\n\n'
            '1. Diem Composite: CTS co diem tong hop la 56.6, xep hang "Mua".\n\n'
            '2. SMDT va Dong luc:\n - SMDT cua CTS: 97.5%, tang tu 88.7%.\n\n'
            '3. Phan ky: Khong co phan ky.'
        )
        messages = [{
            "role": "tool",
            "content": json.dumps({
                "ok": True,
                "ticker": "CTS",
                "group_4key": "Dung song - Dung nganh",
                "recommendation": "MUA - tin hieu thuan ca ma va nganh",
            }, ensure_ascii=False),
        }]

        fixed = ensure_stock_4key_section(final_text, messages)

        self.assertIn('2. Nh', fixed)
        self.assertIn('4 Key', fixed)
        self.assertIn('\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh', fixed)
        self.assertIn('3. SMDT va Dong luc:', fixed)
        self.assertIn('4. Phan ky:', fixed)
        self.assertIn('MUA - t\u00edn hi\u1ec7u thu\u1eadn c\u1ea3 2 chi\u1ec1u', fixed)
        self.assertNotIn('tin hieu thuan ca ma va nganh', fixed)

    def test_keeps_existing_4key_section(self):
        final_text = '1. Diem Composite: 56.6.\n\n2. Nhom 4 Key: Dung song.'
        messages = [{
            "role": "tool",
            "content": json.dumps({"ok": True, "group_4key": "Dung song - Dung nganh"}),
        }]

        self.assertEqual(ensure_stock_4key_section(final_text, messages), final_text)

    def sample_4key_payload(self):
        return {
            "ok": True,
            "ticker": "GEX",
            "date": "2026-07-06",
            "branch": "Ha tang dien",
            "group_4key": "Dung song - Dung nganh",
            "recommendation": "MUA - tin hieu thuan ca ma va nganh",
            "smdt_ticker": 91.9,
            "smdt_ticker_prev": 99.2,
            "ticker_momentum": 45.68,
            "smdt_branch": 50.0,
            "smdt_branch_prev": 40.0,
            "branch_momentum": 10.0,
            "composite": {
                "score": 75,
                "rating": "Mua",
                "co_phan_ky": False,
                "bonus_phan_ky": 0,
            },
        }

    def test_key_nao_question_is_stock_related_and_forces_rules(self):
        for question in ("GEX dang thuoc key nao?", "GEX nay co key gi", "danh gia GEX", "trang thai GEX", "phan tich co phieu GEX"):
            with self.subTest(question=question):
                self.assertTrue(is_stock_related(question))
                self.assertTrue(should_force_rules(question))

    def test_formats_stock_4key_only_question_as_short_answer(self):
        answer = format_stock_4key_answer(self.sample_4key_payload(), user_text="GEX dang thuoc key nao?")

        self.assertEqual(answer, "GEX \u0111ang thu\u1ed9c Nh\u00f3m 4 Key: \"\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh\".")
        self.assertNotIn("Composite", answer)
        self.assertNotIn("SMDT", answer)

    def test_formats_stock_4key_key_gi_question_as_short_answer(self):
        answer = format_stock_4key_answer(self.sample_4key_payload(), user_text="GEX nay co key gi")

        self.assertEqual(answer, "GEX \u0111ang thu\u1ed9c Nh\u00f3m 4 Key: \"\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh\".")
        self.assertNotIn("Composite", answer)
        self.assertNotIn("SMDT", answer)

    def test_formats_stock_4key_yes_no_question_as_natural_short_answer(self):
        answer = format_stock_4key_answer(self.sample_4key_payload(), user_text="GEX co dung song dung nganh khong?")

        self.assertEqual(answer, "C\u00f3, GEX \u0111ang thu\u1ed9c Nh\u00f3m 4 Key \"\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh\".")
        self.assertNotIn("Composite", answer)
        self.assertNotIn("SMDT", answer)

    def test_formats_stock_4key_danh_gia_question_as_short_answer(self):
        answer = format_stock_4key_answer(self.sample_4key_payload(), user_text="danh gia GEX")

        self.assertEqual(answer, "GEX \u0111ang thu\u1ed9c Nh\u00f3m 4 Key: \"\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh\".")
        self.assertNotIn("Composite", answer)
        self.assertNotIn("SMDT", answer)

    def test_formats_stock_4key_trang_thai_question_as_short_answer(self):
        answer = format_stock_4key_answer(self.sample_4key_payload(), user_text="trang thai GEX")

        self.assertEqual(answer, "GEX \u0111ang thu\u1ed9c Nh\u00f3m 4 Key: \"\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh\".")
        self.assertNotIn("Composite", answer)
        self.assertNotIn("SMDT", answer)

    def test_formats_stock_4key_analysis_question_as_short_answer(self):
        answer = format_stock_4key_answer(self.sample_4key_payload(), user_text="phan tich co phieu GEX")

        self.assertEqual(answer, "GEX \u0111ang thu\u1ed9c Nh\u00f3m 4 Key: \"\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh\".")
        self.assertNotIn("Composite", answer)
        self.assertNotIn("SMDT", answer)

    def test_formats_stock_4key_reason_question_as_full_answer(self):
        answer = format_stock_4key_answer(self.sample_4key_payload(), user_text="tai sao GEX thuoc nhom nay")

        self.assertIn("Composite", answer)
        self.assertIn("SMDT", answer)
        self.assertIn("Bonus", answer)
        self.assertIn("MUA - t\u00edn hi\u1ec7u thu\u1eadn c\u1ea3 2 chi\u1ec1u", answer)
        self.assertNotIn("tin hieu thuan ca ma va nganh", answer)

    def test_formats_stock_4key_answer_with_required_group_section(self):
        payload = {
            "ok": True,
            "ticker": "VND",
            "date": "2026-07-02",
            "branch": "Moi gioi chung khoan",
            "group_4key": "Dung song - Dung nganh",
            "recommendation": "MUA - tin hieu thuan ca ma va nganh",
            "smdt_ticker": 7.9,
            "smdt_ticker_prev": -1.7,
            "ticker_momentum": 9.63,
            "smdt_branch": 24.2,
            "smdt_branch_prev": 0.4,
            "branch_momentum": 23.85,
            "composite": {
                "score": 28.8,
                "rating": "Ban manh",
                "co_phan_ky": False,
                "bonus_phan_ky": 0,
                "breakdown": {"dong_tien": 50},
                "notes": ["Thieu du lieu dong tien, tinh trung lap 50 diem"],
            },
        }

        answer = format_stock_4key_answer(payload)

        self.assertIn('2. Nh', answer)
        self.assertIn('4 Key', answer)
        self.assertIn('VND', answer)
        self.assertIn('3. SMDT', answer)
        self.assertIn('5. Bonus', answer)


    def test_detects_4key_payload_without_group_field(self):
        messages = [{
            "role": "tool",
            "content": json.dumps({
                "ok": True,
                "ticker": "VND",
                "ticker_momentum": 9.63,
                "branch_momentum": 23.85,
                "smdt_ticker": 7.9,
                "smdt_branch": 24.2,
                "composite": {"score": 28.8, "rating": "Ban manh"},
            }),
        }]

        payload = latest_stock_4key_payload(messages)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["ticker"], "VND")
    def test_formats_stock_4key_answer_derives_missing_group_from_momentum(self):
        payload = {
            "ok": True,
            "ticker": "VND",
            "date": "2026-07-02",
            "branch": "Moi gioi chung khoan",
            "ticker_momentum": 9.63,
            "branch_momentum": 23.85,
            "smdt_ticker": 7.9,
            "smdt_ticker_prev": -1.7,
            "smdt_branch": 24.2,
            "smdt_branch_prev": 0.4,
            "composite": {"score": 28.8, "rating": "Ban manh", "co_phan_ky": False},
        }

        answer = format_stock_4key_answer(payload)

        self.assertIn('2. Nh', answer)
        self.assertIn('4 Key', answer)
        self.assertIn('\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh', answer)
        self.assertIn('MUA - t\u00edn hi\u1ec7u thu\u1eadn c\u1ea3 2 chi\u1ec1u', answer)
        self.assertNotIn('tin hieu thuan ca ma va nganh', answer)

if __name__ == "__main__":
    unittest.main()

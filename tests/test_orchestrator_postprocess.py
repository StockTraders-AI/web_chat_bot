import json
from datetime import datetime
from types import SimpleNamespace
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.orchestrator import (
    Orchestrator,
    build_case_idea_prompt,
    ensure_stock_4key_section,
    find_matching_case_idea,
    format_branch_drop_answer,
    format_stock_4key_answer,
    latest_stock_4key_payload,
    recent_user_questions_from_messages,
    build_recent_user_questions_context,
    build_contextual_user_text,
    latest_lookup_date_in_text,
    should_force_rules,
    is_stock_related,
    _find_branch_drop_payload,
)


class CaseIdeaPromptTests(unittest.IsolatedAsyncioTestCase):
    def test_definition_song_lon_question_matches_case_name(self):
        cases = [
            {
                "id": 1,
                "name": "Phan tich co phieu",
                "indicators": "SMDT ma",
                "description": "Mo ta phan tich co phieu.",
                "status": "supported",
            },
            {
                "id": 2,
                "name": "Dinh nghia song lon",
                "indicators": "song lon, chan song lon",
                "description": "Song lon la trang thai thi truong co dong tien xac nhan manh.",
                "status": "supported",
            },
        ]

        matched = find_matching_case_idea("song lon la gi", cases)

        self.assertIsNotNone(matched)
        self.assertEqual(matched["id"], 2)

    def test_waiting_case_does_not_match_until_checked_green(self):
        cases = [{
            "id": 2,
            "name": "Dinh nghia song lon",
            "indicators": "song lon",
            "description": "Song lon la prompt rieng admin muon AI dung de tra loi.",
            "status": "waiting",
        }]

        matched = find_matching_case_idea("song lon la gi", cases)

        self.assertIsNone(matched)

    def test_recent_user_questions_keeps_three_previous_user_turns(self):
        messages = [
            {"role": "user", "content": "cau 1"},
            {"role": "assistant", "content": "tra loi 1"},
            {"role": "user", "content": "cau 2"},
            {"role": "user", "content": "cau 3"},
            {"role": "assistant", "content": "tra loi 3"},
            {"role": "user", "content": "cau 4"},
            {"role": "user", "content": "cau hien tai"},
        ]

        questions = recent_user_questions_from_messages(messages, "cau hien tai", limit=3)

        self.assertEqual(questions, ["cau 2", "cau 3", "cau 4"])

    def test_recent_user_questions_context_mentions_date_carryover_rule(self):
        context = build_recent_user_questions_context(["cho mua ngay 09/04/2025 bao nhieu?"])

        self.assertIn("09/04/2025", context)
        self.assertIn("Khong tu sua cau hoi", context)

    async def test_chat_stream_returns_supported_case_description_before_rag(self):
        class FakeMemory:
            def __init__(self):
                self.messages = []

            async def add(self, user_id, role, content):
                self.messages.append({"user_id": user_id, "role": role, "content": content})

            async def recent_messages(self, user_id):
                return [
                    {"role": item["role"], "content": item["content"]}
                    for item in self.messages
                    if item["user_id"] == user_id
                ]

            async def list_case_ideas(self):
                return [{
                    "id": 2,
                    "name": "Dinh nghia song lon",
                    "indicators": "song lon",
                    "description": "Song lon la abcdef",
                    "status": "supported",
                }]

        orch = Orchestrator.__new__(Orchestrator)
        orch.memory = FakeMemory()

        chunks = []
        async for event, data in orch._chat_stream_unlocked(
            user_id="u1",
            user_text="song lon la gi",
            language="vi",
            selected_model="gpt-4o",
        ):
            chunks.append((event, data))

        answer = "".join(data.get("text", "") for event, data in chunks if event == "delta")
        self.assertEqual(answer, "Song lon la abcdef")
        self.assertEqual(chunks[-1][0], "done")

    def test_case_prompt_contains_admin_description(self):
        prompt = build_case_idea_prompt({
            "name": "Dinh nghia song lon",
            "indicators": "song lon",
            "description": "Song lon la mo ta do admin cau hinh.",
            "status": "supported",
        })

        self.assertIn("Mo ta/prompt cua case", prompt)
        self.assertIn("Song lon la mo ta do admin cau hinh.", prompt)
        self.assertIn("Khong nhac den admin", prompt)

    def test_latest_lookup_date_prefers_nearest_recent_question(self):
        context_text = build_contextual_user_text(
            "co xac nhan chan song khong?",
            [
                "cho mua ngay 01/04/2025 bao nhieu?",
                "cho mua ngay 09/04/2025 bao nhieu?",
            ],
        )

        self.assertEqual(latest_lookup_date_in_text(context_text), "2025-04-09")

    def test_get_analyze_wave_tool_uses_date_from_recent_question_context(self):
        class FakeOA:
            def chat(self, **kwargs):
                today = datetime.now().strftime("%Y-%m-%d")
                message = SimpleNamespace(
                    content="",
                    tool_calls=[SimpleNamespace(
                        id="tc1",
                        function=SimpleNamespace(
                            name="getAnalyzeWave",
                            arguments=json.dumps({"date": today}),
                        ),
                    )],
                )
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        class FakeExecutor:
            def __init__(self):
                self.calls = []

            def call(self, operation_id, args, doc_name=None, user_text=None):
                self.calls.append({
                    "operation_id": operation_id,
                    "args": dict(args),
                    "doc_name": doc_name,
                    "user_text": user_text,
                })
                return {"message": "ok"}

        executor = FakeExecutor()
        orch = Orchestrator.__new__(Orchestrator)
        orch.oa = FakeOA()
        orch.executor = executor
        orch.registry = SimpleNamespace(tools=[{
            "type": "function",
            "function": {"name": "getAnalyzeWave", "parameters": {}},
        }])
        context_text = build_contextual_user_text(
            "co xac nhan chan song khong?",
            ["cho mua ngay 09/04/2025 bao nhieu?"],
        )

        _, final_text = orch._run_tool_loop(
            "gpt-4o",
            [{"role": "system", "content": ""}, {"role": "user", "content": context_text}],
            enable_tools=True,
            current_doc="doc",
            user_text=context_text,
        )

        self.assertEqual(final_text, "ok")
        self.assertEqual(executor.calls[0]["args"]["date"], "2025-04-09")

    async def test_build_base_messages_injects_matching_case_description(self):
        class FakeMemory:
            async def recent_messages(self, user_id):
                return [
                    {"role": "user", "content": "cho mua ngay 09/04/2025 bao nhieu?"},
                    {"role": "assistant", "content": "Phien 09/04/2025 co 231 co phieu cho mua."},
                    {"role": "user", "content": "Dinh nghia song lon la gi?"},
                ]

            async def list_case_ideas(self):
                return [{
                    "id": 2,
                    "name": "Dinh nghia song lon",
                    "indicators": "song lon, chan song lon",
                    "description": "Song lon la prompt rieng admin muon AI dung de tra loi.",
                    "status": "supported",
                }]

        class FakeRag:
            def retrieve_best_book(self, query, top_k=3):
                return {"doc_name": None, "score": 0, "chunks": []}

        orch = Orchestrator.__new__(Orchestrator)
        orch.memory = FakeMemory()
        orch.rag = FakeRag()
        orch.classify_query_source = lambda user_text: "BOOKS"

        messages, sources, enable_tools, allowed_apis, current_doc = await orch.build_base_messages(
            user_id="u1",
            user_text="Dinh nghia song lon la gi?",
            language="vi",
        )

        system_text = messages[0]["content"]
        user_text = messages[-1]["content"]
        self.assertIn("CASE PROMPT DO ADMIN THIET LAP", system_text)
        self.assertIn("Song lon la prompt rieng admin muon AI dung de tra loi.", system_text)
        self.assertIn("LICH SU 3 CAU HOI USER GAN NHAT", system_text)
        self.assertIn("09/04/2025", system_text)
        self.assertIn("LICH SU 3 CAU HOI USER GAN NHAT", user_text)
        self.assertIn("09/04/2025", user_text)
        self.assertIn("CAU HOI HIEN TAI - GIU NGUYEN VAN BAN USER", user_text)
        self.assertIn("Dinh nghia song lon la gi?", user_text)
        self.assertNotIn("CAU HOI DA HIEU THEO NGU CANH", user_text)
        self.assertFalse(enable_tools)
        self.assertEqual(sources, [])
        self.assertEqual(allowed_apis, [])
        self.assertIsNone(current_doc)


class OrchestratorPostprocessTests(unittest.TestCase):
    def test_branch_drop_formatter_uses_latest_drop_date(self):
        payload = [{
            "keyName": "Bất động sản dân cư",
            "keyValue": "9-245-249-255-265-",
            "smdts": [
                {"date": "2025-03-27", "smdt": 69.9},
                {"date": "2026-04-07", "smdt": 50.1},
            ],
        }]

        latest = _find_branch_drop_payload(payload)
        answer = format_branch_drop_answer(latest)

        self.assertEqual(latest["date"], "2026-04-07")
        self.assertIn("Bất động sản dân cư", answer)
        self.assertIn("lần gần nhất", answer)
        self.assertIn("2026-04-07", answer)
        self.assertIn("50.1%", answer)
        self.assertIn("70.0%", answer)
        self.assertNotIn("2025-03-27", answer)

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

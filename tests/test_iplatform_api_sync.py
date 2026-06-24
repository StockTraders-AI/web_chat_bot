import unittest

from routes import iplatform_api


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    async def chat_stream(self, **kwargs):
        self.calls.append(kwargs)
        yield "delta", {"text": "đồng bộ"}
        yield "done", {"sources": [{"doc": "rule.txt", "chunk_id": 1}]}


class IPlatformAPISyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.orchestrator = FakeOrchestrator()
        iplatform_api.configure_iplatform_api(lambda: self.orchestrator)

    async def test_packaged_api_uses_shared_orchestrator_pipeline(self):
        payload = iplatform_api.IPlatformChatIn(
            content="PC1 đạt chuẩn mã mạnh khi nào",
            conversation_id="customer-42",
            language="vi",
            model="gpt-4o",
        )

        result = await iplatform_api.iplatform_ai_chat(payload, x_api_key=None)

        self.assertEqual(result["answer"], "đồng bộ")
        self.assertEqual(result["conversation_id"], "customer-42")
        self.assertEqual(result["sources"], [{"doc": "rule.txt", "chunk_id": 1}])
        self.assertEqual(
            self.orchestrator.calls,
            [{
                "user_id": "iplatform:customer-42",
                "user_text": "PC1 đạt chuẩn mã mạnh khi nào",
                "language": "vi",
                "selected_model": "gpt-4o",
            }],
        )

    async def test_legacy_content_only_payload_remains_supported_and_is_isolated(self):
        first = await iplatform_api.iplatform_ai_chat(
            iplatform_api.IPlatformChatIn(content="câu một"),
            x_api_key=None,
        )
        second = await iplatform_api.iplatform_ai_chat(
            iplatform_api.IPlatformChatIn(content="câu hai"),
            x_api_key=None,
        )

        self.assertNotEqual(first["conversation_id"], second["conversation_id"])
        self.assertNotEqual(
            self.orchestrator.calls[0]["user_id"],
            self.orchestrator.calls[1]["user_id"],
        )


if __name__ == "__main__":
    unittest.main()
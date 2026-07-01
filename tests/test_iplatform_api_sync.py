import base64
import hashlib
import hmac
import json
import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core import iplatform_auth
from routes import iplatform_api


SECRET = "test-secret"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_jwt(user_id="customer-42", tenant_id="tenant-a"):
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "exp": 4102444800,
    }
    signing_input = f"{b64url(json.dumps(header).encode())}.{b64url(json.dumps(payload).encode())}"
    signature = hmac.new(SECRET.encode(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{b64url(signature)}"


class FakeMemory:
    def __init__(self):
        self.events = []
        self.accounts = {
            "member1": {
                "id": 12,
                "username": "member1",
                "display_name": "Member One",
                "role": "member",
                "status": "active",
            }
        }

    async def authenticate_account(self, username, password):
        if username == "member1" and password == "password123":
            return dict(self.accounts[username])
        return None

    async def list_ai_token_usage_events(self, since, tenant_id=None, user_id=None):
        rows = []
        for event in self.events:
            created_at = datetime.strptime(event["created_at"], "%Y-%m-%d %H:%M:%S")
            if created_at < since:
                continue
            if tenant_id is not None and event["tenant_id"] != tenant_id:
                continue
            if user_id is not None and event["user_id"] != user_id:
                continue
            rows.append(dict(event))
        return rows

    async def record_ai_token_usage(self, **kwargs):
        row = dict(kwargs)
        created_at = row.pop("created_at", None) or datetime.utcnow()
        row["created_at"] = created_at.strftime("%Y-%m-%d %H:%M:%S")
        self.events.append(row)

    async def list_ai_usage_subjects(self, since):
        grouped = {}
        for event in self.events:
            created_at = datetime.strptime(event["created_at"], "%Y-%m-%d %H:%M:%S")
            if created_at < since:
                continue
            key = (event["tenant_id"], event["user_id"], event["user_key"])
            item = grouped.setdefault(key, {
                "tenant_id": event["tenant_id"],
                "user_id": event["user_id"],
                "user_key": event["user_key"],
                "request_count": 0,
                "total_tokens": 0,
                "last_used_at": event["created_at"],
            })
            item["request_count"] += 1
            item["total_tokens"] += int(event["total_tokens"])
            item["last_used_at"] = max(item["last_used_at"], event["created_at"])
        return list(grouped.values())


class FakeOrchestrator:
    def __init__(self):
        self.calls = []
        self.memory = FakeMemory()

    async def chat_stream(self, **kwargs):
        self.calls.append(kwargs)
        yield "delta", {"text": "??ng b?"}
        yield "done", {
            "sources": [{"doc": "rule.txt", "chunk_id": 1}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
        }


class IPlatformAPISyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        iplatform_auth.IPLATFORM_JWT_SECRET = SECRET
        iplatform_auth.IPLATFORM_JWT_ISSUER = ""
        iplatform_auth.IPLATFORM_JWT_AUDIENCE = ""
        self.orchestrator = FakeOrchestrator()
        iplatform_api.configure_iplatform_api(lambda: self.orchestrator)

    async def login_token(self):
        result = await iplatform_api.iplatform_auth_login(
            iplatform_api.IPlatformLoginIn(
                username="member1",
                password="password123",
            ),
            x_api_key=None,
        )
        return result["access_token"]

    async def test_packaged_api_login_returns_account_jwt(self):
        result = await iplatform_api.iplatform_auth_login(
            iplatform_api.IPlatformLoginIn(
                username="member1",
                password="password123",
            ),
            x_api_key=None,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["token_type"], "Bearer")
        self.assertEqual(result["account"]["id"], 12)
        identity = iplatform_auth.verify_iplatform_jwt(result["access_token"])
        self.assertEqual(identity.user_id, "account:12")
        self.assertEqual(identity.tenant_id, "stocktraders")

    async def test_packaged_api_uses_jwt_identity_and_shared_orchestrator_pipeline(self):
        payload = iplatform_api.IPlatformChatIn(
            content="PC1 ??t chu?n m? m?nh khi n?o",
            conversation_id="thread-1",
            language="vi",
            model="gpt-4o",
        )

        result = await iplatform_api.iplatform_ai_chat(
            payload,
            authorization=f"Bearer {await self.login_token()}",
            x_api_key=None,
        )

        self.assertEqual(result["answer"], "??ng b?")
        self.assertEqual(result["tenant_id"], "stocktraders")
        self.assertEqual(result["user_id"], "account:12")
        self.assertEqual(result["conversation_id"], "thread-1")
        self.assertEqual(result["sources"], [{"doc": "rule.txt", "chunk_id": 1}])
        self.assertEqual(result["usage"]["total_tokens"], 1500)
        self.assertEqual(result["usage"]["limit_5h"], 120000)
        self.assertEqual(
            self.orchestrator.calls,
            [{
                "user_id": "iplatform:stocktraders:account:12:thread-1",
                "user_text": "PC1 ??t chu?n m? m?nh khi n?o",
                "language": "vi",
                "selected_model": "gpt-4o",
            }],
        )

    async def test_packaged_api_defaults_missing_conversation_id(self):
        result = await iplatform_api.iplatform_ai_chat(
            iplatform_api.IPlatformChatIn(content="Gia SSI hom nay?"),
            authorization=f"Bearer {await self.login_token()}",
            x_api_key=None,
        )

        self.assertEqual(result["conversation_id"], "default")
        self.assertEqual(
            self.orchestrator.calls[0]["user_id"],
            "iplatform:stocktraders:account:12:default",
        )
    async def test_jwt_users_are_isolated(self):
        first = await iplatform_api.iplatform_ai_chat(
            iplatform_api.IPlatformChatIn(content="c?u m?t", conversation_id="same-thread"),
            authorization=f"Bearer {make_jwt(user_id='customer-1')}",
            x_api_key=None,
        )
        second = await iplatform_api.iplatform_ai_chat(
            iplatform_api.IPlatformChatIn(content="c?u hai", conversation_id="same-thread"),
            authorization=f"Bearer {make_jwt(user_id='customer-2')}",
            x_api_key=None,
        )

        self.assertNotEqual(first["user_id"], second["user_id"])
        self.assertNotEqual(
            self.orchestrator.calls[0]["user_id"],
            self.orchestrator.calls[1]["user_id"],
        )

    async def test_missing_jwt_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            await iplatform_api.iplatform_ai_chat(
                iplatform_api.IPlatformChatIn(content="c?u h?i", conversation_id="thread"),
                authorization=None,
                x_api_key=None,
            )
        self.assertEqual(ctx.exception.status_code, 401)

    async def test_quota_5h_exceeded_returns_retry_metadata(self):
        self.orchestrator.memory.events.append({
            "tenant_id": "stocktraders",
            "user_id": "account:12",
            "user_key": "iplatform:stocktraders:account:12",
            "conversation_id": "old",
            "request_id": "old",
            "route": "api/ai/chat",
            "model": "gpt-4o",
            "prompt_tokens": 119000,
            "completion_tokens": 0,
            "total_tokens": 119000,
            "created_at": (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        })

        result = await iplatform_api.iplatform_ai_chat(
            iplatform_api.IPlatformChatIn(content="c?u h?i", conversation_id="thread"),
            authorization=f"Bearer {await self.login_token()}",
            x_api_key=None,
        )

        self.assertEqual(result.status_code, 429)
        body = json.loads(result.body.decode("utf-8"))
        self.assertEqual(body["code"], "QUOTA_5H_EXCEEDED")
        self.assertIn("retry_at", body)
        self.assertEqual(len(self.orchestrator.calls), 0)


if __name__ == "__main__":
    unittest.main()


import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from settings import (
    IPLATFORM_JWT_AUDIENCE,
    IPLATFORM_JWT_DEFAULT_TENANT,
    IPLATFORM_JWT_EXPIRES_MINUTES,
    IPLATFORM_JWT_ISSUER,
    IPLATFORM_JWT_SECRET,
)


@dataclass(frozen=True)
class IPlatformIdentity:
    tenant_id: str
    user_id: str
    claims: dict[str, Any]

    @property
    def user_key(self) -> str:
        return f"iplatform:{self.tenant_id}:{self.user_id}"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign_hs256(header: dict[str, Any], claims: dict[str, Any]) -> str:
    if not IPLATFORM_JWT_SECRET:
        raise RuntimeError("IPLATFORM_JWT_SECRET is not configured")

    header_text = _b64url_encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    payload_text = _b64url_encode(
        json.dumps(claims, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{header_text}.{payload_text}".encode("ascii")
    signature = hmac.new(
        IPLATFORM_JWT_SECRET.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{header_text}.{payload_text}.{_b64url_encode(signature)}"


def create_account_access_token(account: dict[str, Any]) -> dict[str, Any]:
    if not account or not account.get("id"):
        raise ValueError("Account is invalid")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires_at = now + timedelta(minutes=IPLATFORM_JWT_EXPIRES_MINUTES)
    user_id = f"account:{account['id']}"
    claims: dict[str, Any] = {
        "sub": user_id,
        "user_id": user_id,
        "account_id": account["id"],
        "username": account.get("username"),
        "role": account.get("role"),
        "tenant_id": IPLATFORM_JWT_DEFAULT_TENANT,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if IPLATFORM_JWT_ISSUER:
        claims["iss"] = IPLATFORM_JWT_ISSUER
    if IPLATFORM_JWT_AUDIENCE:
        claims["aud"] = IPLATFORM_JWT_AUDIENCE

    return {
        "access_token": _sign_hs256({"alg": "HS256", "typ": "JWT"}, claims),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "expires_in": IPLATFORM_JWT_EXPIRES_MINUTES * 60,
        "claims": claims,
    }


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _json_b64url_decode(value: str) -> dict[str, Any]:
    try:
        decoded = _b64url_decode(value)
        data = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise ValueError("JWT is malformed") from exc

    if not isinstance(data, dict):
        raise ValueError("JWT payload is invalid")
    return data


def _expect_string(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"JWT claim {name} is required")
    return text


def _verify_audience(claims: dict[str, Any]):
    if not IPLATFORM_JWT_AUDIENCE:
        return

    aud = claims.get("aud")
    if isinstance(aud, str):
        valid = aud == IPLATFORM_JWT_AUDIENCE
    elif isinstance(aud, list):
        valid = IPLATFORM_JWT_AUDIENCE in {str(item) for item in aud}
    else:
        valid = False

    if not valid:
        raise ValueError("JWT audience is invalid")


def verify_iplatform_jwt(token: str) -> IPlatformIdentity:
    if not IPLATFORM_JWT_SECRET:
        raise RuntimeError("IPLATFORM_JWT_SECRET is not configured")

    parts = (token or "").split(".")
    if len(parts) != 3:
        raise ValueError("JWT is malformed")

    header = _json_b64url_decode(parts[0])
    claims = _json_b64url_decode(parts[1])
    signature = _b64url_decode(parts[2])

    if header.get("alg") != "HS256":
        raise ValueError("JWT alg must be HS256")

    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected = hmac.new(
        IPLATFORM_JWT_SECRET.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("JWT signature is invalid")

    now = datetime.now(timezone.utc).timestamp()
    exp = claims.get("exp")
    if exp is not None and now >= float(exp):
        raise ValueError("JWT is expired")

    nbf = claims.get("nbf")
    if nbf is not None and now < float(nbf):
        raise ValueError("JWT is not active yet")

    if IPLATFORM_JWT_ISSUER and claims.get("iss") != IPLATFORM_JWT_ISSUER:
        raise ValueError("JWT issuer is invalid")
    _verify_audience(claims)

    user_id = _expect_string(claims.get("user_id") or claims.get("sub"), "sub")
    tenant_id = str(
        claims.get("tenant_id")
        or claims.get("tenant")
        or claims.get("org_id")
        or "default"
    ).strip() or "default"

    return IPlatformIdentity(
        tenant_id=tenant_id[:80],
        user_id=user_id[:120],
        claims=claims,
    )

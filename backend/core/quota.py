from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any
from zoneinfo import ZoneInfo

from settings import (
    AI_QUOTA_5H_TOKENS,
    AI_QUOTA_7D_TOKENS,
    AI_QUOTA_ESTIMATED_REQUEST_TOKENS,
)

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
WINDOW_5H = timedelta(hours=5)
WINDOW_7D = timedelta(days=7)


@dataclass
class QuotaExceeded(Exception):
    code: str
    message: str
    retry_at: datetime
    usage: dict[str, Any]
    retry_after_seconds: int = 0


def utcnow() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def parse_db_datetime(value: str | None) -> datetime:
    if not value:
        return utcnow()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return utcnow()


def to_bangkok_iso(value: datetime) -> str:
    aware = value.replace(tzinfo=timezone.utc)
    return aware.astimezone(BANGKOK_TZ).isoformat(timespec="seconds")


def percent_remaining(used: int, limit: int) -> int:
    if limit <= 0:
        return 0
    remaining = max(0, limit - used)
    return max(0, min(100, int(round((remaining / limit) * 100))))


def estimate_token_count(*texts: str) -> int:
    char_count = sum(len(str(text or "")) for text in texts)
    return max(1, ceil(char_count / 4))


def _sum_tokens(events: list[dict[str, Any]]) -> int:
    return sum(int(event.get("total_tokens") or 0) for event in events)


def _reset_at(events: list[dict[str, Any]], window: timedelta, now: datetime) -> datetime:
    if not events:
        return now + window
    return parse_db_datetime(events[0].get("created_at")) + window


def _retry_at(
    events: list[dict[str, Any]],
    window: timedelta,
    limit: int,
    estimated_tokens: int,
    now: datetime,
) -> datetime:
    remaining_used = _sum_tokens(events)
    if remaining_used + estimated_tokens <= limit:
        return now

    for event in events:
        remaining_used -= int(event.get("total_tokens") or 0)
        candidate = parse_db_datetime(event.get("created_at")) + window
        if remaining_used + estimated_tokens <= limit:
            return candidate

    return now + window


class QuotaService:
    def __init__(
        self,
        memory,
        limit_5h: int = AI_QUOTA_5H_TOKENS,
        limit_7d: int = AI_QUOTA_7D_TOKENS,
        default_estimated_tokens: int = AI_QUOTA_ESTIMATED_REQUEST_TOKENS,
    ):
        self.memory = memory
        self.limit_5h = int(limit_5h)
        self.limit_7d = int(limit_7d)
        self.default_estimated_tokens = int(default_estimated_tokens)

    async def usage_summary(
        self,
        tenant_id: str,
        user_id: str,
        estimated_tokens: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or utcnow()
        estimated = int(estimated_tokens or self.default_estimated_tokens)
        events_5h = await self.memory.list_ai_token_usage_events(
            since=now - WINDOW_5H,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        events_7d = await self.memory.list_ai_token_usage_events(
            since=now - WINDOW_7D,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        used_5h = _sum_tokens(events_5h)
        used_7d = _sum_tokens(events_7d)
        reset_5h = _reset_at(events_5h, WINDOW_5H, now)
        reset_7d = _reset_at(events_7d, WINDOW_7D, now)
        retry_5h = _retry_at(events_5h, WINDOW_5H, self.limit_5h, estimated, now)
        retry_7d = _retry_at(events_7d, WINDOW_7D, self.limit_7d, estimated, now)

        return {
            "used_5h": used_5h,
            "limit_5h": self.limit_5h,
            "remaining_5h": max(0, self.limit_5h - used_5h),
            "remaining_percent_5h": percent_remaining(used_5h, self.limit_5h),
            "resets_5h_at": to_bangkok_iso(reset_5h),
            "retry_5h_at": to_bangkok_iso(retry_5h),
            "retry_after_5h_seconds": max(0, int((retry_5h - now).total_seconds())),
            "used_7d": used_7d,
            "limit_7d": self.limit_7d,
            "remaining_7d": max(0, self.limit_7d - used_7d),
            "remaining_percent_7d": percent_remaining(used_7d, self.limit_7d),
            "resets_7d_at": to_bangkok_iso(reset_7d),
            "retry_7d_at": to_bangkok_iso(retry_7d),
            "retry_after_7d_seconds": max(0, int((retry_7d - now).total_seconds())),
            "estimated_next_request_tokens": estimated,
        }

    async def check_quota(
        self,
        tenant_id: str,
        user_id: str,
        estimated_tokens: int | None = None,
    ) -> dict[str, Any]:
        estimated = int(estimated_tokens or self.default_estimated_tokens)
        summary = await self.usage_summary(tenant_id, user_id, estimated_tokens=estimated)

        if summary["used_5h"] + estimated > self.limit_5h:
            retry_after = int(summary.get("retry_after_5h_seconds") or 0)
            raise QuotaExceeded(
                code="QUOTA_5H_EXCEEDED",
                message=f"Ban da dung het quota 5 gio. Co the dung lai luc {summary['retry_5h_at']}.",
                retry_at=utcnow() + timedelta(seconds=retry_after),
                usage=summary,
                retry_after_seconds=retry_after,
            )

        if summary["used_7d"] + estimated > self.limit_7d:
            retry_after = int(summary.get("retry_after_7d_seconds") or 0)
            raise QuotaExceeded(
                code="QUOTA_7D_EXCEEDED",
                message=f"Ban da dung het quota 7 ngay. Co the dung lai tu {summary['retry_7d_at']}, hoac nang cap goi de tiep tuc.",
                retry_at=utcnow() + timedelta(seconds=retry_after),
                usage=summary,
                retry_after_seconds=retry_after,
            )

        return summary

    async def record_usage(
        self,
        tenant_id: str,
        user_id: str,
        user_key: str,
        conversation_id: str,
        request_id: str,
        route: str,
        model: str | None,
        usage: dict[str, Any] | None,
        prompt_text: str,
        answer_text: str,
    ) -> dict[str, Any]:
        usage = usage or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0)

        if total_tokens <= 0:
            total_tokens = max(
                self.default_estimated_tokens,
                estimate_token_count(prompt_text, answer_text),
            )
            prompt_tokens = total_tokens
            completion_tokens = 0

        await self.memory.record_ai_token_usage(
            tenant_id=tenant_id,
            user_id=user_id,
            user_key=user_key,
            conversation_id=conversation_id,
            request_id=request_id,
            route=route,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
        summary = await self.usage_summary(tenant_id, user_id)
        summary.update({
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        })
        return summary

    async def admin_usage_users(self) -> list[dict[str, Any]]:
        since = utcnow() - WINDOW_7D
        subjects = await self.memory.list_ai_usage_subjects(since)
        rows = []
        for subject in subjects:
            summary = await self.usage_summary(subject["tenant_id"], subject["user_id"])
            rows.append({
                "tenant_id": subject["tenant_id"],
                "user_id": subject["user_id"],
                "user_key": subject["user_key"],
                "request_count_7d": int(subject.get("request_count") or 0),
                "total_tokens_7d": int(subject.get("total_tokens") or 0),
                "last_used_at": subject.get("last_used_at"),
                "usage": summary,
            })
        return rows

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Optional, Tuple

ChatEvent = Tuple[str, Dict[str, Any]]


async def stream_standard_chat(
    orchestrator: Any,
    *,
    user_id: str,
    user_text: str,
    language: str = "vi",
    selected_model: Optional[str] = None,
) -> AsyncIterator[ChatEvent]:
    """Single shared standard-chat path for web SSE and packaged API."""
    kwargs = {
        "user_id": user_id,
        "user_text": user_text,
        "language": (language or "vi").strip() or "vi",
        "selected_model": selected_model,
    }

    print("CHAT_RUNTIME_STREAM_START:", {
        "user_id": user_id,
        "text": user_text,
        "language": kwargs["language"],
        "selected_model": selected_model,
    })
    try:
        async for event, data in orchestrator.chat_stream(**kwargs):
            payload = data or {}
            print("CHAT_RUNTIME_STREAM_EVENT:", {
                "event": event,
                "keys": list(payload.keys()) if isinstance(payload, dict) else [],
                "sources": payload.get("sources") if isinstance(payload, dict) else None,
                "text_len": len(str(payload.get("text") or "")) if isinstance(payload, dict) else 0,
            })
            yield event, payload
    finally:
        print("CHAT_RUNTIME_STREAM_END:", {"user_id": user_id, "text": user_text})


async def collect_standard_chat(
    orchestrator: Any,
    *,
    user_id: str,
    user_text: str,
    language: str = "vi",
    selected_model: Optional[str] = None,
) -> tuple[str, Dict[str, Any]]:
    print("COLLECT_STANDARD_CHAT_START:", {"user_id": user_id, "text": user_text})
    answer_parts: list[str] = []
    done_data: Dict[str, Any] = {}

    async for event, data in stream_standard_chat(
        orchestrator,
        user_id=user_id,
        user_text=user_text,
        language=language,
        selected_model=selected_model
    ):
        print("COLLECT_STANDARD_CHAT_EVENT:", {
            "event": event,
            "keys": list((data or {}).keys()) if isinstance(data, dict) else [],
            "sources": (data or {}).get("sources") if isinstance(data, dict) else None,
            "text_len": len(str((data or {}).get("text") or "")) if isinstance(data, dict) else 0,
        })
        if event == "delta":
            answer_parts.append(str(data.get("text") or ""))
            print("COLLECT_STANDARD_CHAT_APPEND_DELTA:", {"parts": len(answer_parts), "answer_len": len("".join(answer_parts))})
        elif event == "done":
            done_data = data or {}
            print("COLLECT_STANDARD_CHAT_CAPTURE_DONE:", done_data)

    answer = "".join(answer_parts).strip()
    print("COLLECT_STANDARD_CHAT_RETURN:", {"answer_len": len(answer), "sources": done_data.get("sources") or [], "usage": done_data.get("usage") or {}})
    return answer, done_data
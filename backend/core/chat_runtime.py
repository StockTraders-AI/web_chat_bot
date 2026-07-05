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
    skip_question_guide: bool = False,
) -> AsyncIterator[ChatEvent]:
    """Single shared standard-chat path for web SSE and packaged API."""
    kwargs = {
        "user_id": user_id,
        "user_text": user_text,
        "language": (language or "vi").strip() or "vi",
        "selected_model": selected_model,
    }
    if skip_question_guide:
        kwargs["skip_question_guide"] = True

    async for event, data in orchestrator.chat_stream(**kwargs):
        yield event, data or {}


async def collect_standard_chat(
    orchestrator: Any,
    *,
    user_id: str,
    user_text: str,
    language: str = "vi",
    selected_model: Optional[str] = None,
    skip_question_guide: bool = False,
) -> tuple[str, Dict[str, Any]]:
    answer_parts: list[str] = []
    done_data: Dict[str, Any] = {}

    async for event, data in stream_standard_chat(
        orchestrator,
        user_id=user_id,
        user_text=user_text,
        language=language,
        selected_model=selected_model,
        skip_question_guide=skip_question_guide,
    ):
        if event == "delta":
            answer_parts.append(str(data.get("text") or ""))
        elif event == "done":
            done_data = data or {}

    return "".join(answer_parts).strip(), done_data
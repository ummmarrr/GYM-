"""Shared Server-Sent Event helpers for progressive text delivery."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

from fastapi.responses import StreamingResponse


def sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def text_chunks(text: str, target_size: int = 28) -> Iterator[str]:
    """Yield readable chunks without breaking words or losing whitespace."""
    chunk = ""
    for part in re.findall(r"\S+\s*", text):
        chunk += part
        if len(chunk) >= target_size:
            yield chunk
            chunk = ""
    if chunk:
        yield chunk


def event_stream(events: Iterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )

"""Reliability helpers for long-lived business SSE streams."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from collections.abc import AsyncIterator


async def iter_lines_with_heartbeat(
    response,
    *,
    heartbeat_seconds: float = 12.0,
) -> AsyncIterator[str | None]:
    """Yield upstream lines and ``None`` while the upstream is temporarily idle.

    ``httpx.Response.aiter_lines()`` can wait a long time for an LLM's next
    event. Awaiting it directly leaves the browser/proxy connection completely
    silent. This keeps the same pending ``__anext__`` task alive while emitting
    heartbeat opportunities; it never cancels and restarts the upstream read.
    """

    iterator = response.aiter_lines().__aiter__()
    pending: asyncio.Task | None = None

    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(iterator.__anext__())

            done, _ = await asyncio.wait({pending}, timeout=heartbeat_seconds)
            if not done:
                yield None
                continue

            try:
                line = pending.result()
            except StopAsyncIteration:
                break

            pending = None
            yield line
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending

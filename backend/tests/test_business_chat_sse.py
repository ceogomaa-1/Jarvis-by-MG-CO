import asyncio

import pytest

from backend.lib.business.sse import iter_lines_with_heartbeat


class _SlowResponse:
    def __init__(self):
        self.iterations = 0

    async def aiter_lines(self):
        self.iterations += 1
        await asyncio.sleep(0.035)
        yield 'data: {"type":"message_start"}'
        await asyncio.sleep(0.02)
        yield 'data: {"type":"message_stop"}'


@pytest.mark.asyncio
async def test_upstream_wait_emits_heartbeats_without_restarting_read():
    response = _SlowResponse()
    events = []
    async for event in iter_lines_with_heartbeat(response, heartbeat_seconds=0.01):
        events.append(event)

    assert None in events
    assert response.iterations == 1
    assert [event for event in events if event is not None] == [
        'data: {"type":"message_start"}',
        'data: {"type":"message_stop"}',
    ]


class _ImmediateResponse:
    async def aiter_lines(self):
        yield "one"
        yield "two"


@pytest.mark.asyncio
async def test_fast_upstream_does_not_add_heartbeats():
    events = []
    async for event in iter_lines_with_heartbeat(_ImmediateResponse(), heartbeat_seconds=1):
        events.append(event)

    assert events == ["one", "two"]

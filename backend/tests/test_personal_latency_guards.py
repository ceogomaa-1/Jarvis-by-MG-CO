"""Critical-path guards for Personal Rue time-to-first-token."""
import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest

from backend import conversation
from backend.lib import sessions
from backend.utils import user_context


def test_message_gap_reuses_history_snapshot_without_second_query():
    created = (datetime.now(timezone.utc) - timedelta(minutes=17)).isoformat()
    assert conversation.get_minutes_since_history([
        {"role": "user", "content": "hello", "created_at": created}
    ]) in (16, 17)
    assert conversation.get_minutes_since_history([]) is None


@pytest.mark.asyncio
async def test_user_time_context_uses_one_cached_preference_lookup(monkeypatch):
    user_context._PREFERENCE_CACHE.clear()
    calls = []

    def fake_lookup(user_id):
        calls.append(user_id)
        data = {"timezone": "America/Toronto", "preferred_name": "Mo"}
        user_context._PREFERENCE_CACHE[user_id] = (time.monotonic(), data)
        return data

    monkeypatch.setattr(user_context, "_get_user_preferences_sync", fake_lookup)
    first = await user_context.format_user_time_context("user-1")
    second = await user_context.format_user_time_context("user-1")

    assert "Mo" in first and "Mo" in second
    assert calls == ["user-1"]


@pytest.mark.asyncio
async def test_session_supabase_transaction_runs_off_event_loop(monkeypatch):
    called = []

    def fake_sync(user_id):
        called.append(user_id)
        now = datetime.now(timezone.utc).isoformat()
        return {
            "session_started_at": now,
            "last_message_at": now,
            "message_count": 1,
            "away_minutes": 0,
        }

    original_to_thread = asyncio.to_thread
    offloaded = []

    async def tracking_to_thread(fn, *args, **kwargs):
        offloaded.append(fn)
        return await original_to_thread(fn, *args, **kwargs)

    monkeypatch.setattr(sessions, "_get_or_create_active_session_sync", fake_sync)
    monkeypatch.setattr(asyncio, "to_thread", tracking_to_thread)

    result = await sessions.get_or_create_active_session("user-1")

    assert result["message_count"] == 1
    assert called == ["user-1"]
    assert offloaded == [fake_sync]

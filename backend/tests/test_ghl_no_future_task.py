"""
P3: contacts-with-no-future-task filter logic.

Live GHL data can't run here, so the pure filtering core (_has_future_task) is the
thing that decides who lands in the CSV — pin it hard. Also confirm the tool is wired.
"""
from datetime import datetime, timedelta, timezone

from backend.lib.business.real_estate.ghl_leads import _has_future_task

NOW = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_no_tasks_means_no_future_task():
    assert _has_future_task([], NOW) is False


def test_future_incomplete_task_counts():
    tasks = [{"completed": False, "dueDate": _iso(NOW + timedelta(days=2))}]
    assert _has_future_task(tasks, NOW) is True


def test_completed_future_task_does_not_count():
    tasks = [{"completed": True, "dueDate": _iso(NOW + timedelta(days=5))}]
    assert _has_future_task(tasks, NOW) is False


def test_overdue_incomplete_task_does_not_count_as_future():
    tasks = [{"completed": False, "dueDate": _iso(NOW - timedelta(days=3))}]
    assert _has_future_task(tasks, NOW) is False


def test_mixed_tasks_with_one_future_counts():
    tasks = [
        {"completed": True, "dueDate": _iso(NOW + timedelta(days=1))},
        {"completed": False, "dueDate": _iso(NOW - timedelta(days=1))},
        {"completed": False, "dueDate": _iso(NOW + timedelta(hours=6))},
    ]
    assert _has_future_task(tasks, NOW) is True


def test_undated_incomplete_task_does_not_count():
    assert _has_future_task([{"completed": False}], NOW) is False


def test_tool_is_registered_and_dispatchable():
    from backend.lib.business.real_estate.tools import REAL_ESTATE_TOOLS, execute_real_estate_tool
    assert "realestate__ghl_contacts_no_future_task" in REAL_ESTATE_TOOLS
    # dispatcher knows the action (returns a ConnectorResult, not "Unknown tool")
    import asyncio
    res = asyncio.run(execute_real_estate_tool("ghl_contacts_no_future_task", {}, "user_test"))
    assert res.ok is False  # no GHL connected in test env
    assert "Unknown Real Estate tool" not in (res.error or "")

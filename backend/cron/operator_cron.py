"""
Nightly Operator Agent cron. Runs at 2:00 AM Toronto time.

Fetches all users with operator_enabled = true and runs the full 4-cycle
operator loop for each. Each user is processed sequentially to avoid
hammering the Anthropic API with concurrent multi-cycle runs.
"""
from datetime import datetime, timezone

from backend.lib.business.brand_config import list_operator_enabled_users
from backend.lib.business.operator.loop import run_operator_for_user


async def run_operator_nightly():
    """Cron entry point. Called by APScheduler at 2:00 AM Toronto."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"OPERATOR_CRON: Starting nightly operator runs at {now_str}")

    users = await list_operator_enabled_users()
    print(f"OPERATOR_CRON: {len(users)} users with operator_enabled=true")

    if not users:
        print("OPERATOR_CRON: No users to run — exiting")
        return

    successes = 0
    for user in users:
        uid = user.get("user_id")
        if not uid:
            continue
        try:
            result = await run_operator_for_user(uid)
            status = result.get("status", "unknown")
            cost = result.get("total_cost_usd", 0)
            actions = result.get("actions_queued", 0)
            print(f"OPERATOR_CRON: user={uid} status={status} cost=${cost:.4f} actions={actions}")
            if status == "complete":
                successes += 1
        except Exception as e:
            print(f"OPERATOR_CRON: user={uid} FAILED with exception: {e}")

    print(f"OPERATOR_CRON: Done — {successes}/{len(users)} runs completed successfully")

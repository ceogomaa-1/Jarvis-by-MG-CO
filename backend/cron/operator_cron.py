"""
Nightly Operator Agent cron. Runs at 2:00 AM Toronto time.

Fetches all users with operator_enabled = true and runs the full 4-cycle
operator loop for each. Each user is processed sequentially to avoid
hammering the Anthropic API with concurrent multi-cycle runs.
"""
from datetime import datetime, timezone

from backend.lib.business.brand_config import list_operator_enabled_users
from backend.lib.business.operator.loop import run_operator_for_user
from backend.lib.business.runtime.store import RuntimeUnavailable, emit_event


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
            # Persist the wake-up before doing work. Duplicate scheduler replicas
            # collapse onto the same daily idempotency key.
            day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            event = await emit_event(
                uid,
                "operator.requested",
                {"user_id": uid, "notify": True, "workflow_key": f"operator-nightly:{uid}:{day_key}"},
                idempotency_key=f"operator-nightly-event:{uid}:{day_key}",
                source="operator_cron",
                subject_type="business",
                subject_id=uid,
            )
            print(f"OPERATOR_CRON: user={uid} queued durable event={event.get('id')}")
            successes += 1
        except RuntimeUnavailable as e:
            # Rolling-release fallback until Batch 77 is applied.
            print(f"OPERATOR_CRON: durable runtime unavailable for {uid}, running legacy path: {e}")
            try:
                result = await run_operator_for_user(uid, notify=True)
                if result.get("status") == "complete":
                    successes += 1
            except Exception as legacy_error:
                print(f"OPERATOR_CRON: user={uid} legacy fallback FAILED: {legacy_error}")
        except Exception as e:
            print(f"OPERATOR_CRON: user={uid} FAILED with exception: {e}")

    print(f"OPERATOR_CRON: Done — {successes}/{len(users)} runs completed successfully")

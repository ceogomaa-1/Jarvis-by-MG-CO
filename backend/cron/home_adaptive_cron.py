"""
Phase 3 adaptive Home cron (Batch 67). Runs nightly at 4:30 AM Toronto — after the
Operator (02:00) has composed fresh Home blocks. For each active business user it
inspects accumulated telemetry and, when a clear workflow pattern has emerged, writes
a single pending reorg suggestion (suggestion-only; the user accepts/rejects/undoes).
"""
from datetime import datetime, timezone

from backend.lib.business.brand_config import list_operator_enabled_users
from backend.lib.business.operator.home_adaptive import detect_and_suggest


async def run_home_adaptive_nightly():
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"HOME_ADAPTIVE_CRON: starting at {now_str}")

    users = await list_operator_enabled_users()
    if not users:
        print("HOME_ADAPTIVE_CRON: no active users — exiting")
        return

    suggested = 0
    for user in users:
        uid = user.get("user_id")
        if not uid:
            continue
        try:
            result = await detect_and_suggest(uid)
            if result.get("suggested"):
                suggested += 1
                print(f"HOME_ADAPTIVE_CRON: user={uid} suggested reorg around {result.get('pattern')}")
        except Exception as e:
            print(f"HOME_ADAPTIVE_CRON: user={uid} failed: {e}")

    print(f"HOME_ADAPTIVE_CRON: done — {suggested}/{len(users)} users received a suggestion")

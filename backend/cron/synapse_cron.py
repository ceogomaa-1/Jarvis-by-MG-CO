"""
Weekly Golden Synapses cron. Runs Sunday 3:00 AM Toronto time.

For every active user (same eligibility as the Morning Queue), runs one
on-demand-equivalent synapse discovery pass. generate_synapses() naturally
no-ops if the user already triggered one today via the manual button.
"""
from datetime import datetime, timezone

from backend.lib.business.mind.synapses import generate_synapses
from backend.lib.business.morning_queue import list_active_users


async def run_weekly_synapse_generation():
    """Cron entry point. Called by APScheduler Sunday 03:00 Toronto."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"SYNAPSE_CRON: Starting weekly synapse generation at {now_str}")

    users = await list_active_users()
    print(f"SYNAPSE_CRON: {len(users)} active users to process")

    generated = skipped = failed = 0
    for user_id in users:
        try:
            result = await generate_synapses(user_id)
            if result.get("rate_limited"):
                skipped += 1
            elif result.get("synapses"):
                generated += 1
            print(f"SYNAPSE_CRON: user={user_id} synapses={len(result.get('synapses', []))} rate_limited={result.get('rate_limited')}")
        except Exception as e:
            failed += 1
            print(f"SYNAPSE_CRON: user={user_id} failed: {e}")

    print(f"SYNAPSE_CRON: Done — {generated} with new synapses, {skipped} skipped, {failed} failed")

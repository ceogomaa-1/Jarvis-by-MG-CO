"""External-pinger dispatch endpoint for scheduled emails (Feature 1)."""
from fastapi import APIRouter

from backend.cron.scheduled_emails_cron import run_scheduled_emails

router = APIRouter()


@router.post("/business/email/_dispatch")
async def dispatch_scheduled_emails():
    """Dispatch target for an external cron pinger (cron-job.org / UptimeRobot,
    every ~60s). Sends any business_scheduled_emails rows whose send_at has
    passed — same logic as the APScheduler job, callable on-demand so emails
    go out within ~1 minute regardless of the dyno's sleep state."""
    processed = await run_scheduled_emails()
    return {"status": "ok", "processed": processed}

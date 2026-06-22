import sys

# Debug/log prints throughout this codebase use non-ASCII characters (→, em-dashes,
# etc.). Production runs under UTF-8, but on Windows stdout often defaults to cp1252,
# which raises UnicodeEncodeError deep inside request handlers and turns a working
# request into "Hit a snag on my end." Force UTF-8 so logging never breaks a request.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("jarvis")
from backend.utils.env import ANTHROPIC_API_KEY
from backend.routes.chat import router as chat_router
from backend.routes.memory_routes import router as memory_router
from backend.routes.user_routes import router as user_router
from backend.routes.proactive_routes import router as proactive_router
from backend.routes.notes_routes import router as notes_router
from backend.routes.study_routes import router as study_router
from backend.routes.push_routes import router as push_router
from backend.routes.voice_routes import router as voice_router
from backend.routes.history_routes import router as history_router
from backend.routes.google_auth_routes import router as google_auth_router
from backend.routes.files_routes import router as files_router
from backend.cron.briefing import run_morning_briefings, CHECKIN_HOUR, CHECKIN_MINUTE, CHECKIN_TZ
from backend.cron.notes_reminders import run_notes_reminders
from backend.routes.local_agent_routes import router as local_agent_router
from backend.routes.business.chat import router as business_chat_router
from backend.routes.business.show_me_how import router as business_show_me_how_router
from backend.routes.business.create import router as business_create_router
from backend.routes.business.create_actions import router as business_create_actions_router
from backend.routes.business.proactive_routes import router as business_proactive_router
from backend.routes.business.connections import router as business_connections_router
from backend.routes.business.brand_routes import router as business_brand_router
from backend.routes.business.operator_routes import router as business_operator_router
from backend.routes.business.conversations import router as business_conversations_router
from backend.cron.operator_cron import run_operator_nightly
from backend.cron.business_risk_cron import run_business_risk_briefings
from backend.routes.user_preferences import router as user_preferences_router
from backend.routes.export import router as export_router
from backend.routes.documents import router as documents_router
from backend.routes.announcements_routes import router as announcements_router
from backend.routes.business.readiness_routes import router as business_readiness_router
from backend.routes.business.onboarding_routes import router as business_onboarding_router
from backend.routes.business.documents import router as business_documents_router
from backend.routes.business.knowledge_routes import router as business_knowledge_router
from backend.routes.business.morning_queue_routes import router as business_morning_queue_router
from backend.routes.business.mind import router as business_mind_router
from backend.routes.business.feedback_routes import router as business_feedback_router
from backend.routes.business.email_routes import router as business_email_router
from backend.routes.business.crm_routes import router as business_crm_router
from backend.cron.synapse_cron import run_weekly_synapse_generation
from backend.cron.scheduled_emails_cron import run_scheduled_emails

if not ANTHROPIC_API_KEY:
    raise RuntimeError(
        "ANTHROPIC_API_KEY is not set. Add it to .env.local or .env in the project root."
    )


scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create data dirs and start cron scheduler on startup."""
    for path in [
        "data/user_models",
        "data/last_interaction",
        "data/notes",
    ]:
        os.makedirs(path, exist_ok=True)

    scheduler.add_job(
        run_morning_briefings,
        CronTrigger(hour=CHECKIN_HOUR, minute=CHECKIN_MINUTE, timezone=CHECKIN_TZ),
        id="morning_briefings",
        replace_existing=True,
    )
    scheduler.add_job(
        run_business_risk_briefings,
        CronTrigger(hour=6, minute=0, timezone="America/Toronto"),
        id="business_risk_briefings",
        replace_existing=True,
    )
    scheduler.add_job(
        run_operator_nightly,
        CronTrigger(hour=2, minute=0, timezone="America/Toronto"),
        id="operator_nightly",
        replace_existing=True,
    )
    scheduler.add_job(
        run_weekly_synapse_generation,
        CronTrigger(day_of_week="sun", hour=3, minute=0, timezone="America/Toronto"),
        id="weekly_synapses",
        replace_existing=True,
    )
    scheduler.add_job(
        run_notes_reminders,
        CronTrigger(minute="*"),
        id="notes_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        run_scheduled_emails,
        CronTrigger(minute="*"),
        id="scheduled_emails",
        replace_existing=True,
    )
    scheduler.start()
    print(f"CRON: Scheduler started — personal daily check-in at {CHECKIN_HOUR:02d}:{CHECKIN_MINUTE:02d} {CHECKIN_TZ}, business risk at 06:00, operator at 02:00, synapses Sun 03:00 Toronto, notes reminders every 1 min (also reachable via POST /api/notes/_dispatch for external pinger), scheduled emails every 1 min (also reachable via POST /api/business/email/_dispatch)")

    yield

    scheduler.shutdown()
    print("CRON: Scheduler stopped")


app = FastAPI(title="Jarvis by MG&CO", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    """Safety net ONLY for exceptions that currently fall through to a raw Starlette
    500. FastAPI handles HTTPException and validation errors separately, so this does
    not alter any route that already returns a proper status. It just turns an
    otherwise-uncaught crash into a clean, consistent JSON 500 (no traceback/secrets
    leaked to the client) and logs the real error server-side."""
    logger.exception(f"UNHANDLED: {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": "Something went wrong on our end. Please try again."},
    )


@app.options("/{path:path}")
async def options_handler(path: str):
    return {"status": "ok"}


app.include_router(chat_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(proactive_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
app.include_router(study_router, prefix="/api")
app.include_router(push_router, prefix="/api")
app.include_router(voice_router, prefix="/api")
app.include_router(history_router, prefix="/api")
app.include_router(google_auth_router, prefix="/api")
app.include_router(files_router, prefix="/api")
app.include_router(local_agent_router)  # no prefix — WebSocket at /ws/local-agent
app.include_router(business_chat_router, prefix="/api")
app.include_router(business_show_me_how_router, prefix="/api")
app.include_router(business_create_router, prefix="/api")
app.include_router(business_create_actions_router, prefix="/api")
app.include_router(business_proactive_router, prefix="/api")
app.include_router(business_connections_router, prefix="/api")
app.include_router(business_brand_router, prefix="/api")
app.include_router(business_operator_router, prefix="/api")
app.include_router(business_conversations_router, prefix="/api")
app.include_router(user_preferences_router, prefix="/api")
app.include_router(export_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(business_readiness_router, prefix="/api")
app.include_router(business_onboarding_router, prefix="/api")
app.include_router(business_documents_router, prefix="/api")
app.include_router(business_knowledge_router, prefix="/api")
app.include_router(business_morning_queue_router, prefix="/api")
app.include_router(business_mind_router, prefix="/api")
app.include_router(business_feedback_router, prefix="/api")
app.include_router(business_email_router, prefix="/api")
app.include_router(business_crm_router, prefix="/api")
app.include_router(announcements_router, prefix="/api")


@app.on_event("startup")
async def print_routes():
    for route in app.routes:
        if hasattr(route, "methods"):
            print(f"ROUTE: {route.methods} {route.path}")


@app.get("/")
async def root():
    return {"status": "Jarvis is alive"}


@app.get("/health")
async def health():
    """Instant 200 — used by the frontend to warm up the Render dyno before the first chat message."""
    return {"status": "ok"}

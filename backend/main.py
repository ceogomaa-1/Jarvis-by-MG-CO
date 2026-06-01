import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.utils.env import ANTHROPIC_API_KEY
from backend.routes.chat import router as chat_router
from backend.routes.memory_routes import router as memory_router
from backend.routes.user_routes import router as user_router
from backend.routes.proactive_routes import router as proactive_router
from backend.routes.notes_routes import router as notes_router
from backend.routes.voice_routes import router as voice_router
from backend.routes.history_routes import router as history_router
from backend.routes.google_auth_routes import router as google_auth_router
from backend.routes.files_routes import router as files_router
from backend.cron.briefing import run_morning_briefings
from backend.routes.local_agent_routes import router as local_agent_router
from backend.routes.business.chat import router as business_chat_router
from backend.routes.business.show_me_how import router as business_show_me_how_router
from backend.routes.business.create import router as business_create_router
from backend.routes.business.create_actions import router as business_create_actions_router
from backend.routes.user_preferences import router as user_preferences_router
from backend.routes.export import router as export_router
from backend.routes.documents import router as documents_router

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
        "data/proactive",
        "data/last_interaction",
        "data/notes",
    ]:
        os.makedirs(path, exist_ok=True)

    scheduler.add_job(
        run_morning_briefings,
        CronTrigger(hour=8, minute=0, timezone="America/Toronto"),
        id="morning_briefings",
        replace_existing=True,
    )
    scheduler.start()
    print("CRON: Scheduler started — morning briefings at 08:00 Toronto")

    yield

    scheduler.shutdown()
    print("CRON: Scheduler stopped")


app = FastAPI(title="Jarvis by MG&CO", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.options("/{path:path}")
async def options_handler(path: str):
    return {"status": "ok"}


app.include_router(chat_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(proactive_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
app.include_router(voice_router, prefix="/api")
app.include_router(history_router, prefix="/api")
app.include_router(google_auth_router, prefix="/api")
app.include_router(files_router, prefix="/api")
app.include_router(local_agent_router)  # no prefix — WebSocket at /ws/local-agent
app.include_router(business_chat_router, prefix="/api")
app.include_router(business_show_me_how_router, prefix="/api")
app.include_router(business_create_router, prefix="/api")
app.include_router(business_create_actions_router, prefix="/api")
app.include_router(user_preferences_router, prefix="/api")
app.include_router(export_router, prefix="/api")
app.include_router(documents_router, prefix="/api")


@app.on_event("startup")
async def print_routes():
    for route in app.routes:
        if hasattr(route, "methods"):
            print(f"ROUTE: {route.methods} {route.path}")


@app.get("/")
async def root():
    return {"status": "Jarvis is alive"}

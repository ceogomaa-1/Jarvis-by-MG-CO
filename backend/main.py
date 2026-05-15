import os
from contextlib import asynccontextmanager

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

if not ANTHROPIC_API_KEY:
    raise RuntimeError(
        "ANTHROPIC_API_KEY is not set. Add it to .env.local or .env in the project root."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create all data directories on startup — required on Railway's ephemeral filesystem."""
    for path in [
        "data/user_models",
        "data/proactive",
        "data/last_interaction",
        "data/notes",
    ]:
        os.makedirs(path, exist_ok=True)
    yield


app = FastAPI(title="Jarvis by MG&CO", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(proactive_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
app.include_router(voice_router, prefix="/api")
app.include_router(history_router, prefix="/api")


@app.get("/")
async def root():
    return {"status": "Jarvis is alive"}

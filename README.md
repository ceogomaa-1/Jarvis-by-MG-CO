# Rue by MG&CO

A next-generation personal AI that learns you over time, initiates conversations proactively, and acts as a fully agentic assistant. Inspired by Samantha from "Her."

## How to run

**Prerequisites:** Python 3.11+, Node.js 18+, dependencies installed.

**Install backend dependencies:**
```bash
pip install -r requirements.txt
```

**Install frontend dependencies:**
```bash
cd frontend && npm install
```

**Start everything:**
```bash
bash start.sh
```

Or manually:
```bash
# Terminal 1 — backend
cd backend && uvicorn main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open **http://localhost:3000** to talk to Rue.

---

## Phase Tracker

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 0 | ✅ Complete | Project scaffold, backend API, frontend UI, Claude integration |
| Phase 1 | Pending | Mem0 memory — Rue remembers every conversation |
| Phase 2 | Pending | User model — dynamic profile that compounds over time |
| Phase 3 | Pending | Proactive triggers — Rue initiates conversations |
| Phase 4 | Pending | Agentic tools — Rue takes actions in the world |
| Phase 5 | Pending | Voice interface |
| Phase 6 | Pending | Mobile app |

---

## Architecture

```
browser → Next.js (port 3000)
             ↓ POST /api/chat
         FastAPI (port 8000)
             ↓
         llm.py → jarvis_think()   ← ONLY place Claude SDK is called
             ↓
         Anthropic Claude API
```

**Critical rule:** Every LLM call goes through `backend/llm.py:jarvis_think()`. No other file touches the Anthropic SDK. Swap to a local Llama model by changing only that one function.

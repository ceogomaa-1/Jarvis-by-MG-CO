from pathlib import Path
from dotenv import load_dotenv
import os

# Try .env.local first, fall back to .env (both are in the project root, one level above backend/)
_root = Path(__file__).resolve().parent.parent.parent
_env_local = _root / ".env.local"
_env = _root / ".env"

if _env_local.exists():
    load_dotenv(dotenv_path=_env_local)
else:
    load_dotenv(dotenv_path=_env)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MEM0_API_KEY = os.getenv("MEM0_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

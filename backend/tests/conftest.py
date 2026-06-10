import os
import sys
import types
from pathlib import Path

from dotenv import load_dotenv

# Load throwaway test credentials BEFORE any backend module (which load real
# .env/.env.local via backend.utils.env on first import) gets imported by a test.
# override=True ensures these placeholders win even though backend.utils.env's
# own load_dotenv() call (override=False) runs afterward for any keys not
# listed in .env.test.
_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=_ROOT / ".env.test", override=True)

# backend.memory instantiates mem0.MemoryClient(api_key=...) at MODULE IMPORT
# TIME, and MemoryClient.__init__ makes a live HTTP call to api.mem0.ai/v1/ping
# to validate the key, raising ValueError if it fails (see STABILITY-AUDIT.md
# defect list — this is a real production hard-boot-dependency on Mem0, not
# just a test problem). Stub it out so importing backend.main never hits the
# network or requires a real key, mirroring the existing suite's approach to
# the supabase SDK.
if "mem0" not in sys.modules:
    _fake_mem0 = types.ModuleType("mem0")

    class _FakeMemoryClient:
        def __init__(self, *args, **kwargs):
            pass

        def add(self, *args, **kwargs):
            return {"results": []}

        def search(self, *args, **kwargs):
            return {"results": []}

        def get_all(self, *args, **kwargs):
            return {"results": []}

    _fake_mem0.MemoryClient = _FakeMemoryClient
    sys.modules["mem0"] = _fake_mem0

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture(scope="session")
def client():
    """TestClient against the full app (Personal + Business routes), .env.test config."""
    with TestClient(app) as c:
        yield c

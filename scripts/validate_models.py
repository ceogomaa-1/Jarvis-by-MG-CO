"""
Ping the Anthropic API with every model constant used in Rue OS1.
Exits 0 if all pass, 1 if any fail.

Usage:
  ANTHROPIC_API_KEY=sk-... python scripts/validate_models.py
"""
import os
import sys
import anthropic

from backend.lib.business.model_router import HAIKU, SONNET, OPUS

MODELS = [HAIKU, SONNET, OPUS]


def ping(model_id: str) -> bool:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    try:
        msg = client.messages.create(
            model=model_id,
            max_tokens=4,
            messages=[{"role": "user", "content": "hi"}],
        )
        print(f"  ✓  {model_id}  →  stop_reason={msg.stop_reason}")
        return True
    except anthropic.APIStatusError as e:
        print(f"  ✗  {model_id}  →  {e.status_code} {e.message}")
        return False
    except Exception as e:
        print(f"  ✗  {model_id}  →  {e}")
        return False


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    print("Validating Anthropic model IDs…\n")
    results = [ping(m) for m in MODELS]
    print()
    if all(results):
        print("All models reachable.")
        sys.exit(0)
    else:
        failed = [m for m, ok in zip(MODELS, results) if not ok]
        print(f"FAILED: {failed}")
        sys.exit(1)

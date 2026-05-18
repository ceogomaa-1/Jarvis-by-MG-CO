from pathlib import Path


def get_soul() -> str:
    soul_path = Path(__file__).resolve().parent.parent.parent / "SOUL.md"
    if soul_path.exists():
        return soul_path.read_text(encoding="utf-8")
    return ""

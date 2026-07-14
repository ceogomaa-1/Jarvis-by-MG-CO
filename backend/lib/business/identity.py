"""Canonical identity helpers for the business side of Rue.

The browser still sends ``user_<uuid-without-dashes>`` while most mature OS1
tables use a real Postgres UUID. New OS1 code must cross that boundary here so
the conversion does not keep spreading through every repository.
"""
from uuid import UUID


def user_id_to_uuid(user_id: str) -> str:
    """Return a normalized UUID string from either supported app identity shape.

    Raises ValueError for malformed identities. Failing closed is important for
    service-role queries because those queries bypass row-level security.
    """
    raw = (user_id or "").strip().removeprefix("user_").replace("-", "")
    if len(raw) != 32:
        raise ValueError("Invalid user identity")
    try:
        return str(UUID(hex=raw))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Invalid user identity") from exc


def uuid_to_app_user_id(user_uuid: str) -> str:
    return "user_" + UUID(str(user_uuid)).hex


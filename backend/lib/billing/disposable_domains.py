"""Disposable / temp-email domain blocklist for OS1 signup (anti-abuse).

A new OS1 account on a throwaway domain can't farm a trial. This is a curated set of the
most common disposable providers — not exhaustive, but it stops the obvious abuse. The list
can be extended via the OS1_EXTRA_DISPOSABLE_DOMAINS env (comma-separated) without a deploy.
"""
import os

# Common disposable / temporary mailbox providers (lowercased, bare domain).
_DISPOSABLE = {
    "0-mail.com", "10minutemail.com", "20minutemail.com", "33mail.com", "guerrillamail.com",
    "guerrillamail.info", "guerrillamail.biz", "guerrillamail.net", "guerrillamail.org",
    "sharklasers.com", "grr.la", "spam4.me", "mailinator.com", "mailinator.net",
    "mailinator2.com", "trashmail.com", "trashmail.net", "trash-mail.com", "trashmail.me",
    "yopmail.com", "yopmail.net", "yopmail.fr", "cool.fr.nf", "jetable.org", "nospam.ze.tc",
    "temp-mail.org", "temp-mail.io", "tempmail.com", "tempmailo.com", "tempr.email",
    "tmail.ws", "tmpmail.org", "tmpmail.net", "throwawaymail.com", "throwam.com",
    "getnada.com", "nada.email", "dispostable.com", "fakeinbox.com", "fakemailgenerator.com",
    "maildrop.cc", "mailnesia.com", "mintemail.com", "mohmal.com", "mytemp.email",
    "emailondeck.com", "spamgourmet.com", "mailcatch.com", "mailexpire.com", "mailnull.com",
    "mailtemp.net", "moakt.com", "luxusmail.org", "burnermail.io", "10mail.org",
    "anonbox.net", "harakirimail.com", "incognitomail.com", "tempinbox.com", "inboxbear.com",
    "inboxkitten.com", "wegwerfmail.de", "wegwerfmail.net", "spambox.us", "spambog.com",
    "discard.email", "discardmail.com", "mailde.de", "mail-temporaire.fr", "fake-box.com",
    "vomoto.com", "tafmail.com", "armyspy.com", "cuvox.de", "dayrep.com", "einrot.com",
    "fleckens.hu", "gustr.com", "jourrapide.com", "rhyta.com", "superrito.com", "teleworm.us",
}


def _normalize_domain(domain: str) -> str:
    return (domain or "").strip().lower().lstrip("@")


def extra_domains() -> set:
    raw = os.getenv("OS1_EXTRA_DISPOSABLE_DOMAINS", "")
    return {_normalize_domain(d) for d in raw.split(",") if d.strip()}


def is_disposable(email: str) -> bool:
    """True if the email's domain is a known disposable/temp-mail provider."""
    email = (email or "").strip().lower()
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1]
    return domain in _DISPOSABLE or domain in extra_domains()


def normalize_email(email: str) -> str:
    """Identity-normalize an email for trial dedupe.

    Lowercases, and for Gmail/Googlemail collapses dot-tricks and +tags
    (foo.bar+spam@gmail.com == foobar@gmail.com) — the classic serial-trial vector.
    """
    email = (email or "").strip().lower()
    if "@" not in email:
        return email
    local, domain = email.rsplit("@", 1)
    if domain in ("gmail.com", "googlemail.com"):
        local = local.split("+", 1)[0].replace(".", "")
        domain = "gmail.com"
    else:
        local = local.split("+", 1)[0]
    return f"{local}@{domain}"

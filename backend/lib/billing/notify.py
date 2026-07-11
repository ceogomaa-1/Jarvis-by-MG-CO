"""Contact-form delivery for the OS1 'Talk to Sales' / Contact Us page.

Primary: Resend (RESEND_API_KEY) → emails CONTACT_TO (default info@mgcotechnologies.com).
Fallback: if Resend isn't configured or fails, log the submission so nothing is ever lost
(same resilience pattern as the waitlist's Notion-or-log fallback). Returns a dict the route
can surface so the UI can confirm delivery.
"""
import os

import httpx

CONTACT_TO = os.getenv("CONTACT_TO", "info@mgcotechnologies.com")
CONTACT_FROM = os.getenv("CONTACT_FROM", "Rue OS1 <onboarding@resend.dev>")


async def send_contact(*, name: str, email: str, company: str = "", message: str = "",
                       phone: str = "") -> dict:
    subject = f"[OS1 Contact] {name}" + (f" — {company}" if company else "")
    text = (
        f"New OS1 Contact / Tailored inquiry\n\n"
        f"Name:    {name}\n"
        f"Email:   {email}\n"
        f"Phone:   {phone or '—'}\n"
        f"Company: {company or '—'}\n\n"
        f"Message:\n{message or '—'}\n"
    )

    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        print("[OS1 CONTACT] (no RESEND_API_KEY — logging)", {
            "name": name, "email": email, "company": company, "phone": phone, "message": message,
        })
        return {"ok": True, "delivered": False, "fallback": "log"}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "from": CONTACT_FROM,
                    "to": [CONTACT_TO],
                    "reply_to": email,
                    "subject": subject,
                    "text": text,
                },
                timeout=15.0,
            )
        if resp.status_code < 300:
            return {"ok": True, "delivered": True}
        print("[OS1 CONTACT] Resend error:", resp.status_code, resp.text[:300])
        return {"ok": True, "delivered": False, "fallback": "log"}
    except Exception as e:
        print("[OS1 CONTACT] Resend exception:", e)
        return {"ok": True, "delivered": False, "fallback": "log"}

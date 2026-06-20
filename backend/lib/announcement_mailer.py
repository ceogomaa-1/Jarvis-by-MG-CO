"""
Batch 56 — branded "What's New" announcement email, sent on publish.

Reuses the Resend channel + dark-luxury template from personal_mailer (same
verified mgcodashboard.com domain, display name "Jarvis OS1", hosted logo). One
email per published announcement; the per-row idempotency guard lives in the
caller (announcement_email_log), not here.

send_announcement_email() returns True only on a confirmed 2xx from Resend.
"""

import html as _html

import httpx

from backend.lib.personal_mailer import (
    APP_URL,
    LOGO_URL,
    RESEND_API_KEY,
    RESEND_FROM,
    _ACCENT,
    _BG,
    _INK,
    _SANS,
    _SERIF,
    is_configured,
)

_TAG_LABELS = {
    "New Feature": "✨ New Feature",
    "Improvement": "△ Improvement",
    "Fix": "✓ Fix",
}


def _md_to_html(body: str) -> str:
    """Tiny, safe markdown → HTML for the email body. Escapes everything first,
    then re-introduces a small, fixed set of formatting (paragraphs, **bold**,
    *italic*, `code`, and - bullet lists). No raw HTML from the author survives,
    so a malformed/hostile body can't inject markup into the email."""
    import re

    def inline(text: str) -> str:
        text = _html.escape(text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
        text = re.sub(
            r"`(.+?)`",
            r'<code style="background:rgba(243,234,217,0.08);padding:1px 5px;border-radius:4px;">\1</code>',
            text,
        )
        return text

    blocks: list[str] = []
    bullets: list[str] = []

    def flush_bullets():
        if bullets:
            items = "".join(
                f'<li style="margin:0 0 6px;">{inline(b)}</li>' for b in bullets
            )
            blocks.append(
                f'<ul style="margin:0 0 14px;padding-left:20px;color:{_INK};'
                f'font-family:{_SANS};font-size:14px;line-height:1.6;">{items}</ul>'
            )
            bullets.clear()

    for raw_line in body.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            flush_bullets()
            continue
        if line.startswith(("- ", "* ")):
            bullets.append(line[2:].strip())
            continue
        flush_bullets()
        blocks.append(
            f'<p style="margin:0 0 14px;color:{_INK};font-family:{_SANS};'
            f'font-size:15px;line-height:1.65;">{inline(line)}</p>'
        )
    flush_bullets()
    return "".join(blocks)


def _build_html(
    title: str,
    body: str,
    tag: str,
    media_url: str | None,
    cta_label: str | None,
    cta_url: str | None,
) -> str:
    tag_label = _TAG_LABELS.get(tag, "✨ New")
    cta_text = cta_label or "See what's new"
    cta_href = cta_url or APP_URL

    media_row = (
        f'<tr><td style="padding:0 32px 8px;">'
        f'<img src="{_html.escape(media_url, quote=True)}" alt="" width="100%" '
        f'style="display:block;border-radius:12px;border:1px solid rgba(243,234,217,0.08);" /></td></tr>'
        if media_url else ""
    )

    return f"""<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background-color:{_BG};">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{_BG};padding:40px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" style="max-width:480px;background-color:{_BG};border:1px solid rgba(243,234,217,0.08);border-radius:16px;overflow:hidden;">
            <tr>
              <td align="center" style="padding:32px 32px 16px;background-color:#000000;">
                <img src="{LOGO_URL}" alt="Jarvis OS1" width="220" style="display:block;margin:0 auto;border:0;" />
              </td>
            </tr>
            <tr>
              <td align="center" style="padding:10px 32px 24px;background-color:#000000;">
                <div style="font-family:{_SANS};color:rgba(243,234,217,0.45);font-size:11px;letter-spacing:0.2em;text-transform:uppercase;">What's new in Jarvis</div>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px;">
                <div style="border-top:1px solid rgba(243,234,217,0.08);"></div>
              </td>
            </tr>
            <tr>
              <td style="padding:28px 32px 14px;">
                <div style="font-family:{_SANS};color:{_ACCENT};font-size:11px;letter-spacing:0.22em;text-transform:uppercase;margin-bottom:14px;">{tag_label}</div>
                <div style="font-family:{_SERIF};color:{_INK};font-size:24px;line-height:1.3;margin-bottom:18px;">{_html.escape(title)}</div>
              </td>
            </tr>
            {media_row}
            <tr>
              <td style="padding:6px 32px 4px;">
                {_md_to_html(body)}
              </td>
            </tr>
            <tr>
              <td align="center" style="padding:22px 32px 32px;">
                <a href="{_html.escape(cta_href, quote=True)}" style="display:inline-block;background-color:{_ACCENT};color:#1a0e08;text-decoration:none;font-family:{_SANS};font-size:12px;font-weight:600;letter-spacing:0.2em;text-transform:uppercase;padding:14px 36px;border-radius:8px;">{_html.escape(cta_text)}</a>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px;">
                <div style="border-top:1px solid rgba(243,234,217,0.08);"></div>
              </td>
            </tr>
            <tr>
              <td align="center" style="padding:20px 32px 28px;">
                <div style="font-family:{_SANS};color:rgba(243,234,217,0.35);font-size:10px;letter-spacing:0.03em;line-height:1.7;">MG&amp;CO Technologies &middot; You're receiving this because you use Jarvis OS1.</div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _build_text(title: str, body: str, cta_url: str | None) -> str:
    lines = [
        "JARVIS OS1 — WHAT'S NEW",
        "",
        title,
        "",
        body.strip(),
        "",
        f"See what's new: {cta_url or APP_URL}",
        "",
        "--",
        "MG&CO Technologies. You're receiving this because you use Jarvis OS1.",
    ]
    return "\n".join(lines)


async def send_announcement_email(
    to_email: str,
    title: str,
    body: str,
    tag: str = "New Feature",
    media_url: str | None = None,
    cta_label: str | None = None,
    cta_url: str | None = None,
) -> bool:
    """Send one branded announcement email via Resend.

    Returns True only on a confirmed 2xx response from Resend.
    """
    if not is_configured() or not to_email:
        return False

    subject = f"✨ New in Jarvis — {title}"
    html_body = _build_html(title, body, tag, media_url, cta_label, cta_url)
    text_body = _build_text(title, body, cta_url)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": RESEND_FROM,
                    "to": [to_email],
                    "subject": subject,
                    "html": html_body,
                    "text": text_body,
                },
            )
        if 200 <= resp.status_code < 300:
            return True
        print(f"ANNOUNCE MAILER: Resend send failed ({resp.status_code}): {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"ANNOUNCE MAILER: failed to send to {to_email}: {e}")
        return False

"""Branded HTML shell shared by every outbound email.

Table-based layout because major mail clients do not reliably support
flexbox/grid.
"""

from app.foundation.config import get_settings

BRAND_COLOR = "#0a54e0"  # SOSNET brand blue, same as the dashboard
TEXT_COLOR = "#101d2a"
MUTED_COLOR = "#556b7a"


def render_email(
    *,
    preheader: str,
    heading: str,
    body_html: str,
    cta_label: str | None = None,
    cta_url: str | None = None,
) -> str:
    """body_html is trusted markup: callers must escape any user-supplied
    values before passing it in.

    Blue SOSNET band with the logo on a white chip, white card for the
    content, gradient call to action with the plain link repeated below it
    (some clients block buttons), and a footer."""
    # The public address comes from the environment, so moving to a new
    # domain is a .env change and never a code change.
    base_url = get_settings().public_app_base_url.rstrip("/")
    base_host = base_url.split("://", 1)[-1]
    logo_url = f"{base_url}/email-logo.png"
    cta_block = ""
    if cta_label and cta_url:
        cta_block = f"""
          <tr>
            <td align="center" style="padding: 12px 36px 8px 36px;">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" bgcolor="{BRAND_COLOR}" style="border-radius:14px; background:{BRAND_COLOR};
                      background-image:linear-gradient(100deg,#216eff 0%,#1eb1ff 55%,#47e2ff 100%);">
                    <a href="{cta_url}" style="display:inline-block; padding:16px 34px; color:#ffffff; text-decoration:none;
                       font-weight:800; font-size:15px; letter-spacing:0.02em; border-radius:14px;">
                      {cta_label}
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding: 6px 36px 26px 36px;">
              <p style="margin:0; font-size:12px; line-height:1.5; color:{MUTED_COLOR}; text-align:center;">
                Se il pulsante non funziona, copia questo indirizzo nel browser:<br>
                <a href="{cta_url}" style="color:{BRAND_COLOR}; word-break:break-all;">{cta_url}</a>
              </p>
            </td>
          </tr>"""

    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{heading}</title>
</head>
<body style="margin:0; padding:0; background:#ecf0f4; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="display:none; max-height:0; overflow:hidden; opacity:0;">{preheader}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ecf0f4; padding:28px 14px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px; background:#ffffff; border-radius:22px; overflow:hidden; box-shadow:0 18px 40px -24px rgba(0, 26, 60,0.45);">
          <tr>
            <td align="center" bgcolor="#0943b0" style="background:#0943b0; background-image:radial-gradient(120% 140% at 50% -30%, #2f78ff 0%, #0b57e6 30%, #073e9a 70%, #05295c 100%); padding:30px 24px 26px 24px;">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" bgcolor="#ffffff" style="background:#ffffff; border-radius:16px; padding:10px 18px;">
                    <img src="{logo_url}" alt="SOS Affiliate" width="166" height="36" style="display:block; height:36px; width:166px; border:0;">
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:30px 36px 6px 36px;">
              <h1 style="margin:0 0 14px 0; font-size:22px; line-height:1.25; font-weight:800; color:{TEXT_COLOR};">{heading}</h1>
              <div style="font-size:15px; line-height:1.65; color:{TEXT_COLOR};">
                {body_html}
              </div>
            </td>
          </tr>
          {cta_block}
          <tr>
            <td style="padding:18px 36px 26px 36px; border-top:1px solid #e4ebf3; background:#f6f8fb;">
              <p style="margin:0; font-size:12px; line-height:1.6; color:{MUTED_COLOR};">
                <strong style="color:{BRAND_COLOR};">SOSNET</strong> &middot;
                <a href="{base_url}" style="color:{MUTED_COLOR}; text-decoration:none;">{base_host}</a><br>
                Email automatica: non rispondere a questo indirizzo. Per assistenza apri un ticket dalla tua area riservata.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

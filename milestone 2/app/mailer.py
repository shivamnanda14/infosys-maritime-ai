"""Mailer utility for FreightQuote AI.
Sends emails (OTP codes, alerts) via SMTP using Gmail app password.
"""
import ssl
import smtplib
from email.message import EmailMessage
import config

def creds():
    return config.EMAIL_ADDRESS, config.EMAIL_PASSWORD

def configured():
    em, pw = creds()
    return bool(em and pw)

def send(to, subject, body, attachments=(), html=None):
    """Send an email. Returns (ok, message). Never prints secrets or codes."""
    em, pw = creds()
    if not (em and pw):
        return False, "Email OTP is not configured, use the security question"
    try:
        m = EmailMessage()
        m["Subject"] = subject
        m["From"] = em
        m["To"] = to
        m.set_content(body)
        if html:
            m.add_alternative(html, subtype="html")
        for fn, data, mt in attachments:
            m.add_attachment(data, maintype=mt.split("/")[0], subtype=mt.split("/")[1], filename=fn)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=20) as s:
            s.login(em, pw)
            s.send_message(m)
        return True, f"Sent to {to}"
    except Exception as e:
        return False, "Email could not be sent. Check the sender configuration and retry later."


def otp_html(username, code):
    from html import escape
    return f"""<!doctype html><html><body style="margin:0;background:#eef5f3;font-family:Arial,sans-serif;color:#173b3d"><table role="presentation" width="100%" cellpadding="24"><tr><td align="center"><table role="presentation" width="100%" style="max-width:520px;background:white;border-radius:16px" cellpadding="32"><tr><td><p style="color:#137e78;font-weight:bold">FreightQuote AI</p><h1 style="font-size:26px">Reset your password</h1><p>Hello {escape(str(username))},</p><p>Enter this code to continue your password reset.</p><p style="background:#edf7f4;padding:22px;text-align:center;font-size:32px;letter-spacing:8px;font-weight:bold">{escape(str(code))}</p><p>This code expires in <strong>5 minutes</strong>. Do not share it with anyone.</p><p style="color:#607674;font-size:13px">If you did not request a reset, you can ignore this email. Your password has not changed.</p></td></tr></table></td></tr></table></body></html>"""

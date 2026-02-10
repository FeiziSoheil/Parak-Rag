"""Send emails (e.g. verification) via SMTP."""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    EMAIL_FROM,
    BASE_URL,
)


def send_verification_email(
    to_email: str,
    verification_token: str,
    username: str,
    verification_code: str | None = None,
    code_expire_minutes: int = 15,
) -> None:
    """Send verification email with numeric code only (no link). Raises on SMTP failure."""
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("SMTP is not configured (SMTP_USER/SMTP_PASSWORD missing)")

    code = verification_code or ""
    text_body = (
        f"Hi {username},\n\n"
        "Please verify your email by entering this code on the website:\n\n"
        f"  {code}\n\n"
        f"This code expires in {code_expire_minutes} minutes.\n\n"
        "If you did not create an account, you can ignore this email."
    )
    html_body = (
        f"<p>Hi {username},</p>\n"
        "<p>Please verify your email by entering this code on the website:</p>\n"
        f'<p style="font-size:1.5em;letter-spacing:0.2em;font-weight:bold;">{code}</p>\n'
        f"<p>This code expires in {code_expire_minutes} minutes.</p>\n"
        "<p>If you did not create an account, you can ignore this email.</p>"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Verify your email address"
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(EMAIL_FROM, to_email, msg.as_string())


def send_email_change_email(to_new_email: str, confirm_url: str, username: str) -> None:
    """Send email to new address with link to confirm change."""
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("SMTP is not configured")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Confirm your new email address"
    msg["From"] = EMAIL_FROM
    msg["To"] = to_new_email
    text_body = (
        f"Hi {username},\n\n"
        "You requested to change your email. Click the link below to confirm:\n\n"
        f"{confirm_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    html_body = (
        f"<p>Hi {username},</p>\n"
        "<p>You requested to change your email. Click the link below to confirm:</p>\n"
        f'<p><a href="{confirm_url}">{confirm_url}</a></p>\n'
        "<p>If you did not request this, you can ignore this email.</p>"
    )
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(EMAIL_FROM, to_new_email, msg.as_string())


def send_password_change_code_email(to_email: str, code: str, username: str, expire_minutes: int = 15) -> None:
    """Send 6-digit code for password change."""
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("SMTP is not configured")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Password change verification code"
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    text_body = (
        f"Hi {username},\n\n"
        f"Your verification code for password change is: {code}\n\n"
        f"This code expires in {expire_minutes} minutes.\n\n"
        "If you did not request this, please secure your account."
    )
    html_body = (
        f"<p>Hi {username},</p>\n"
        "<p>Your verification code for password change is:</p>\n"
        f'<p style="font-size:1.5em;letter-spacing:0.2em;font-weight:bold;">{code}</p>\n'
        f"<p>This code expires in {expire_minutes} minutes.</p>\n"
        "<p>If you did not request this, please secure your account.</p>"
    )
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(EMAIL_FROM, to_email, msg.as_string())

"""Send emails via SMTP."""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM


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

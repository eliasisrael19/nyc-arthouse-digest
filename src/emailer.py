from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

from src.config import AppConfig


def send_email(config: AppConfig, subject: str, html_body: str, text_body: str) -> None:
    smtp = config.smtp
    missing = [
        name
        for name, value in {
            "SMTP_HOST": smtp.host,
            "SMTP_USERNAME": smtp.username,
            "SMTP_PASSWORD": smtp.password,
            "SMTP_SENDER": smtp.sender,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing SMTP configuration: {', '.join(missing)}")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp.sender
    # Keep recipient addresses private by sending to the actual list via SMTP
    # while showing only the sender in the visible To header.
    msg["To"] = smtp.sender

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(smtp.host, smtp.port, timeout=30) as server:
        if smtp.use_starttls:
            server.starttls()
        server.login(smtp.username, smtp.password)
        server.sendmail(smtp.sender, config.recipients, msg.as_string())

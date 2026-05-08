"""SMTP delivery."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from weekly_brief.config import AppConfig


def send_email(
    cfg: AppConfig,
    subject: str,
    body: str,
    html_attachment: str | None = None,
    html_filename: str = "weekly-brief.html",
) -> None:
    msg = EmailMessage()
    msg["From"] = cfg.smtp.user
    msg["To"] = cfg.smtp.to
    msg["Subject"] = subject
    msg.set_content(body)
    if html_attachment:
        msg.add_attachment(
            html_attachment.encode("utf-8"),
            maintype="text",
            subtype="html",
            filename=html_filename,
        )
    ctx = ssl.create_default_context()
    if cfg.smtp.port == 465:
        with smtplib.SMTP_SSL(cfg.smtp.host, cfg.smtp.port, context=ctx, timeout=30) as s:
            s.login(cfg.smtp.user, cfg.smtp.password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg.smtp.host, cfg.smtp.port, timeout=30) as s:
            s.ehlo()
            if s.has_extn("STARTTLS"):
                s.starttls(context=ctx)
                s.ehlo()
            s.login(cfg.smtp.user, cfg.smtp.password)
            s.send_message(msg)

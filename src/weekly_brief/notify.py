"""SMTP delivery of the weekly digest."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from weekly_brief.config import AppConfig

log = logging.getLogger(__name__)


def _ensure_pwd(cfg: AppConfig) -> str:
    try:
        return cfg.smtp.password
    except RuntimeError as exc:
        raise RuntimeError(
            f"SMTP password env var '{cfg.smtp.password_env}' is empty. "
            f"Fill it in your .env (project) or ~/.config/weekly-brief/secrets.env (launchd). "
            f"Original: {exc}"
        ) from exc


def send_email(
    cfg: AppConfig,
    subject: str,
    body: str,
    html_attachment: str | None = None,
    html_filename: str = "weekly-brief.html",
    debug: bool = False,
) -> None:
    """Send mail with `body` as plain text. If `html_attachment` is given, attach it as a file."""
    pwd = _ensure_pwd(cfg)
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
    log.info("SMTP connect %s:%s as %s", cfg.smtp.host, cfg.smtp.port, cfg.smtp.user)
    if cfg.smtp.port == 465:
        with smtplib.SMTP_SSL(cfg.smtp.host, cfg.smtp.port, context=ctx, timeout=30) as s:
            if debug:
                s.set_debuglevel(1)
            s.login(cfg.smtp.user, pwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg.smtp.host, cfg.smtp.port, timeout=30) as s:
            if debug:
                s.set_debuglevel(1)
            s.ehlo()
            if s.has_extn("STARTTLS"):
                s.starttls(context=ctx)
                s.ehlo()
            s.login(cfg.smtp.user, pwd)
            s.send_message(msg)


def ping(cfg: AppConfig, debug: bool = False) -> None:
    """Send a tiny test email so user can confirm SMTP creds."""
    send_email(cfg, "weekly-brief test", "test ✓ — SMTP works.", debug=debug)

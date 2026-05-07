from pathlib import Path

import pytest

from weekly_brief.config import load_config


def _write_cfg(tmp: Path) -> Path:
    p = tmp / "config.yaml"
    p.write_text(
        """
timezone: Europe/Paris
output_dir: ~/Documents/WeeklyBrief
imap:
  host: imap.example.com
  user: u@e.com
  password_env: IMAP_PWD
smtp:
  host: smtp.example.com
  user: u@e.com
  password_env: SMTP_PWD
  to: u@e.com
calendars:
  - name: Work
    category: work
    url: https://example.com/w.ics
vips:
  - vip@example.com
  - "@boss.com"
""",
        encoding="utf-8",
    )
    return p


def test_load_basic(tmp_path, monkeypatch):
    p = _write_cfg(tmp_path)
    monkeypatch.setenv("WEEKLY_BRIEF_CONFIG", str(p))
    cfg = load_config()
    assert cfg.timezone == "Europe/Paris"
    assert cfg.imap.host == "imap.example.com"
    assert cfg.smtp.to == "u@e.com"
    assert "vip@example.com" in cfg.vip_emails
    assert "boss.com" in cfg.vip_domains


def test_password_raises_when_unset(tmp_path, monkeypatch):
    p = _write_cfg(tmp_path)
    monkeypatch.setenv("WEEKLY_BRIEF_CONFIG", str(p))
    cfg = load_config()
    # Clear after load (load_dotenv may re-populate from a project-local .env file).
    monkeypatch.delenv("IMAP_PWD", raising=False)
    with pytest.raises(RuntimeError):
        _ = cfg.imap.password

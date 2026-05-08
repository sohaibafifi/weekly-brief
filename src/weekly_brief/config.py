"""Config loading: YAML file + environment-derived secrets."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

CONFIG_ENV_VAR = "WEEKLY_BRIEF_CONFIG"
DEFAULT_CONFIG_PATHS = [
    Path.cwd() / "config.yaml",
    Path.home() / ".config" / "weekly-brief" / "config.yaml",
]


class IMAPConfig(BaseModel):
    host: str
    port: int = 993
    user: str
    password_env: str = "IMAP_PWD"
    inbox: str = "INBOX"
    sent: str = "Sent"

    @property
    def password(self) -> str:
        pwd = os.environ.get(self.password_env, "")
        if not pwd:
            raise RuntimeError(f"IMAP password env var '{self.password_env}' not set")
        return pwd


class SMTPConfig(BaseModel):
    host: str
    port: int = 465
    user: str
    password_env: str = "SMTP_PWD"
    to: str

    @property
    def password(self) -> str:
        pwd = os.environ.get(self.password_env, "")
        if not pwd:
            raise RuntimeError(f"SMTP password env var '{self.password_env}' not set")
        return pwd


class CalendarConfig(BaseModel):
    name: str
    category: str
    url: str | None = None
    urls: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_url_or_urls(self):
        if not self.url and not self.urls:
            raise ValueError(f"Calendar '{self.name}' must define 'url' or 'urls'")
        return self

    def feeds(self) -> list[tuple[str, str]]:
        """Return [(source_name, url), …]. Multi-URL entries get '<name> #N' suffix."""
        items: list[tuple[str, str]] = []
        all_urls = list(self.urls) + ([self.url] if self.url else [])
        if len(all_urls) == 1:
            items.append((self.name, all_urls[0]))
        else:
            for i, u in enumerate(all_urls, start=1):
                items.append((f"{self.name} #{i}", u))
        return items


class MailRules(BaseModel):
    flagged: bool = True
    vip: bool = True
    awaiting_reply: bool = True
    awaiting_reply_lookback_days: int = 14
    vip_lookback_days: int = 14
    flagged_lookback_days: int = 30


class LLMFeatures(BaseModel):
    week_narrative: bool = True
    per_meeting_prep: bool = True


class NotionConfig(BaseModel):
    enabled: bool = False
    api_key_env: str = "NOTION_API_KEY"
    database_id: str = ""
    title_prop: str = "Name"
    week_prop: str = "Week"
    summary_prop: str = "Summary"  # rich_text property; "" to disable
    url_prop: str = ""  # optional URL property; "" to disable
    notion_version: str = "2022-06-28"
    base_url: str = "https://api.notion.com/v1"

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) or None


class LLMConfig(BaseModel):
    provider: Literal["mistral"] = "mistral"
    model: str = "mistral-large-latest"
    api_key_env: str = "MISTRAL_API_KEY"
    features: LLMFeatures = Field(default_factory=LLMFeatures)
    max_tokens_total: int = 4000
    base_url: str = "https://api.mistral.ai/v1"

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) or None


class AppConfig(BaseModel):
    timezone: str = "Europe/Paris"
    output_dir: Path = Path("~/Documents/WeeklyBrief")
    locale: str = "fr"
    work_hours: dict[str, list[list[str]]] = Field(default_factory=dict)
    imap: IMAPConfig
    smtp: SMTPConfig
    calendars: list[CalendarConfig] = Field(default_factory=list)
    vips: list[str] = Field(default_factory=list)
    mail_rules: MailRules = Field(default_factory=MailRules)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    notion: NotionConfig = Field(default_factory=NotionConfig)

    @field_validator("output_dir", mode="before")
    @classmethod
    def _expand(cls, v):
        return Path(str(v)).expanduser()

    @property
    def vip_emails(self) -> set[str]:
        return {v.lower() for v in self.vips if not v.startswith("@")}

    @property
    def vip_domains(self) -> set[str]:
        return {v.lstrip("@").lower() for v in self.vips if v.startswith("@")}


def _resolve_path(explicit: Path | None) -> Path:
    if explicit:
        return explicit.expanduser()
    env = os.environ.get(CONFIG_ENV_VAR)
    if env:
        return Path(env).expanduser()
    for p in DEFAULT_CONFIG_PATHS:
        if p.exists():
            return p
    raise FileNotFoundError(
        f"No config found. Looked at: {CONFIG_ENV_VAR} env, {DEFAULT_CONFIG_PATHS}"
    )


def load_config(path: Path | None = None) -> AppConfig:
    """Load YAML config + .env into AppConfig. Idempotent."""
    load_dotenv(override=False)
    cfg_path = _resolve_path(path)
    with cfg_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return AppConfig.model_validate(raw)

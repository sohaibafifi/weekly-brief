"""Build Brief view-model + render HTML/Markdown via Jinja2 (locale-aware)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from babel.dates import format_date as babel_format_date
from babel.dates import format_datetime as babel_format_datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape

from weekly_brief.calendars import group_by_category, group_by_day
from weekly_brief.models import Event, Slot, Thread
from weekly_brief.textutil import fmt_hours

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
if not TEMPLATES_DIR.exists():
    TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Babel skeleton patterns. See https://unicode.org/reports/tr35/tr35-dates.html#Date_Format_Patterns
DEFAULT_DATE_PATTERN = "EEE d MMM HH:mm"
HEADER_DATE_PATTERN = "EEE d MMM"
DAY_LABEL_PATTERN = "EEEE d MMM"
TIME_PATTERN = "HH:mm"
GENERATED_PATTERN = "EEE d MMM HH:mm zzz"

CATEGORY_LABELS = {
    "fr": {"work": "Travail", "personal": "Personnel", "family": "Famille"},
    "en": {"work": "Work", "personal": "Personal", "family": "Family"},
}


@dataclass
class Brief:
    week_iso: str
    week_start: datetime
    week_end: datetime
    timezone: str
    locale: str
    narrative: str
    events_by_category: dict[str, list[Event]]
    events_by_day: dict[str, list[Event]]
    free_slots_by_day: dict[str, list[Slot]]
    mail_attention: dict[str, list]
    meetings_with_prep: list[Event]
    generated_at: datetime


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _fmt_dt_factory(tz: ZoneInfo, locale: str):
    def _fmt(dt: datetime, pattern: str = DEFAULT_DATE_PATTERN) -> str:
        return babel_format_datetime(dt.astimezone(tz), pattern, locale=locale)

    return _fmt


def _fmt_time_factory(tz: ZoneInfo, locale: str):
    def _fmt(dt: datetime) -> str:
        return babel_format_datetime(dt.astimezone(tz), TIME_PATTERN, locale=locale)

    return _fmt


def _category_label_factory(locale: str):
    table = CATEGORY_LABELS.get(locale, CATEGORY_LABELS["en"])

    def _label(cat: str) -> str:
        return table.get(cat, cat.capitalize())

    return _label


def build_brief(
    week_iso: str,
    week_start: datetime,
    week_end: datetime,
    timezone: str,
    events: list[Event],
    free_slots_by_day: dict[str, list[Slot]],
    flagged: list,
    vip: list,
    awaiting: list[Thread],
    narrative: str,
    locale: str = "fr",
) -> Brief:
    return Brief(
        week_iso=week_iso,
        week_start=week_start,
        week_end=week_end,
        timezone=timezone,
        locale=locale,
        narrative=narrative,
        events_by_category=group_by_category(events),
        events_by_day=group_by_day(events, timezone),
        free_slots_by_day=free_slots_by_day,
        mail_attention={"flagged": flagged, "vip": vip, "awaiting_reply": awaiting},
        meetings_with_prep=[ev for ev in events if ev.attendees],
        generated_at=datetime.now(ZoneInfo(timezone)),
    )


def _day_label_factory(locale: str):
    def _label(iso: str, pattern: str = DAY_LABEL_PATTERN) -> str:
        return babel_format_date(date.fromisoformat(iso), pattern, locale=locale)

    return _label


def _bind_filters(env: Environment, brief: Brief) -> None:
    tz = ZoneInfo(brief.timezone)
    env.filters["fmt_dt"] = _fmt_dt_factory(tz, brief.locale)
    env.filters["fmt_time"] = _fmt_time_factory(tz, brief.locale)
    env.filters["cat_label"] = _category_label_factory(brief.locale)
    env.filters["day_label"] = _day_label_factory(brief.locale)
    env.filters["dur_h"] = fmt_hours
    env.globals["HEADER_DATE_PATTERN"] = HEADER_DATE_PATTERN
    env.globals["GENERATED_PATTERN"] = GENERATED_PATTERN
    env.globals["DAY_LABEL_PATTERN"] = DAY_LABEL_PATTERN


def render_html(brief: Brief) -> str:
    env = _env()
    _bind_filters(env, brief)
    name = "brief.fr.html.j2" if brief.locale == "fr" else "brief.html.j2"
    if not (TEMPLATES_DIR / name).exists():
        name = "brief.html.j2"
    return env.get_template(name).render(brief=brief)


def render_markdown(brief: Brief) -> str:
    env = _env()
    _bind_filters(env, brief)
    name = "brief.fr.md.j2" if brief.locale == "fr" else "brief.md.j2"
    if not (TEMPLATES_DIR / name).exists():
        name = "brief.md.j2"
    return env.get_template(name).render(brief=brief)

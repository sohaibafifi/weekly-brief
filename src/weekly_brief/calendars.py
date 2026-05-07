"""Fetch ICS, expand recurrence, build events + free-slots."""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import recurring_ical_events
from icalendar import Calendar

from weekly_brief.config import AppConfig, CalendarConfig
from weekly_brief.models import Event, Slot
from weekly_brief.timeutil import iter_days, parse_hhmm

log = logging.getLogger(__name__)

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def fetch_ics(url: str, timeout: float = 30.0) -> bytes:
    r = httpx.get(url, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.content


def _ensure_dt(value, tz: ZoneInfo) -> tuple[datetime, bool]:
    """Normalize an ical date/datetime to TZ-aware datetime + all-day flag."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=tz), False
        return value.astimezone(tz), False
    if isinstance(value, date):
        return datetime.combine(value, time(0, 0), tz), True
    raise TypeError(f"Unexpected ical date type: {type(value)!r}")


def _attendees(component) -> list[str]:
    raw = component.get("ATTENDEE")
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    for a in items:
        s = str(a)
        if s.upper().startswith("MAILTO:"):
            s = s[7:]
        if s:
            out.append(s.lower())
    return out


def _organizer(component) -> str:
    org = component.get("ORGANIZER")
    if not org:
        return ""
    s = str(org)
    if s.upper().startswith("MAILTO:"):
        s = s[7:]
    return s.lower()


def parse_calendar(
    data: bytes,
    cal_cfg: CalendarConfig,
    start: datetime,
    end: datetime,
    tz: ZoneInfo,
    source_name: str | None = None,
) -> list[Event]:
    text = data.decode("utf-8", errors="replace") if isinstance(data, (bytes, bytearray)) else data
    cal = Calendar.from_ical(text)
    events: list[Event] = []
    src = source_name or cal_cfg.name
    for occ in recurring_ical_events.of(cal).between(start, end):
        try:
            s, all_day = _ensure_dt(occ.get("DTSTART").dt, tz)
            e_dt = occ.get("DTEND")
            if e_dt is None:
                e = s + timedelta(hours=1) if not all_day else s + timedelta(days=1)
            else:
                e, _ = _ensure_dt(e_dt.dt, tz)
        except Exception as exc:
            log.warning("Skip event in %s: %s", src, exc)
            continue
        events.append(
            Event(
                uid=str(occ.get("UID", "")) + "@" + s.isoformat(),
                start=s,
                end=e,
                title=str(occ.get("SUMMARY", "(no title)")),
                location=str(occ.get("LOCATION", "")),
                attendees=_attendees(occ),
                organizer=_organizer(occ),
                category=cal_cfg.category,
                source_name=src,
                description=str(occ.get("DESCRIPTION", "")),
                all_day=all_day,
            )
        )
    return events


def collect_events(
    cfg: AppConfig, start: datetime, end: datetime, fetch=fetch_ics
) -> list[Event]:
    """Pull all calendars (each may have multiple URLs), expand in [start, end).
    `fetch` injectable for tests; receives a URL, returns bytes."""
    z = ZoneInfo(cfg.timezone)
    out: list[Event] = []
    for c in cfg.calendars:
        for source_name, url in c.feeds():
            try:
                data = fetch(url)
            except Exception as exc:
                log.warning("Failed to fetch %s (%s): %s", source_name, url, exc)
                continue
            try:
                out.extend(parse_calendar(data, c, start, end, z, source_name=source_name))
            except Exception as exc:
                log.warning("Failed to parse %s: %s", source_name, exc)
    out.sort(key=lambda ev: ev.start)
    return out


# ── free-slot computation ────────────────────────────────────────────────────


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: x[0])
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        ls, le = merged[-1]
        if s <= le:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return merged


def _windows_for_day(
    d: date, work_hours: dict[str, list[list[str]]], tz: ZoneInfo
) -> list[tuple[datetime, datetime]]:
    name = WEEKDAYS[d.weekday()]
    spans = work_hours.get(name, [])
    out: list[tuple[datetime, datetime]] = []
    for span in spans:
        if len(span) != 2:
            continue
        s = datetime.combine(d, parse_hhmm(span[0]), tz)
        e = datetime.combine(d, parse_hhmm(span[1]), tz)
        if e > s:
            out.append((s, e))
    return out


def free_slots(
    events: list[Event],
    start: datetime,
    end: datetime,
    work_hours: dict[str, list[list[str]]],
    tz_name: str,
    min_minutes: int = 30,
) -> dict[str, list[Slot]]:
    """Compute available windows per day. Skip all-day events when subtracting."""
    z = ZoneInfo(tz_name)
    busy = [(ev.start.astimezone(z), ev.end.astimezone(z)) for ev in events if not ev.all_day]
    busy = _merge_intervals(busy)
    by_day: dict[str, list[Slot]] = {}
    for d in iter_days(start, end):
        windows = _windows_for_day(d, work_hours, z)
        slots: list[Slot] = []
        for ws, we in windows:
            cursor = ws
            for bs, be in busy:
                if be <= ws or bs >= we:
                    continue
                if bs > cursor:
                    slots.append(Slot(cursor, min(bs, we)))
                cursor = max(cursor, be)
                if cursor >= we:
                    break
            if cursor < we:
                slots.append(Slot(cursor, we))
        slots = [s for s in slots if s.duration_min >= min_minutes]
        by_day[d.isoformat()] = slots
    return by_day


def group_by_category(events: list[Event]) -> dict[str, list[Event]]:
    out: dict[str, list[Event]] = {}
    for ev in events:
        out.setdefault(ev.category, []).append(ev)
    return out


def group_by_day(events: list[Event], tz_name: str) -> dict[str, list[Event]]:
    z = ZoneInfo(tz_name)
    out: dict[str, list[Event]] = {}
    for ev in events:
        key = ev.start.astimezone(z).date().isoformat()
        out.setdefault(key, []).append(ev)
    return out

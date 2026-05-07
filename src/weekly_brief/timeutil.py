"""TZ-aware datetime helpers + ISO-week boundaries."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def tz(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def now_in(tz_name: str) -> datetime:
    return datetime.now(tz(tz_name))


def week_bounds(ref: datetime, tz_name: str) -> tuple[datetime, datetime]:
    """Return (monday_00:00, next_monday_00:00) for ISO week of `ref`, in given TZ."""
    z = tz(tz_name)
    local = ref.astimezone(z)
    monday = local.date() - timedelta(days=local.weekday())
    start = datetime.combine(monday, time(0, 0), z)
    end = start + timedelta(days=7)
    return start, end


def next_week_bounds(ref: datetime, tz_name: str) -> tuple[datetime, datetime]:
    """Bounds for the week starting after `ref` (i.e. coming Monday)."""
    _, cur_end = week_bounds(ref, tz_name)
    return cur_end, cur_end + timedelta(days=7)


def iso_label(start: datetime) -> str:
    iso = start.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def iter_days(start: datetime, end: datetime):
    """Iterate over distinct local dates between [start, end)."""
    cur: date = start.date()
    last: date = (end - timedelta(seconds=1)).date()
    while cur <= last:
        yield cur
        cur += timedelta(days=1)


def parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))

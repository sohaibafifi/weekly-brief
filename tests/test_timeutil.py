from datetime import datetime
from zoneinfo import ZoneInfo

from weekly_brief.timeutil import (
    iso_label,
    iter_days,
    next_week_bounds,
    parse_hhmm,
    week_bounds,
)


def test_week_bounds_starts_on_monday():
    ref = datetime(2026, 5, 7, 14, 30, tzinfo=ZoneInfo("Europe/Paris"))  # Thursday
    s, e = week_bounds(ref, "Europe/Paris")
    assert s.weekday() == 0
    assert s.hour == 0 and s.minute == 0
    assert (e - s).days == 7


def test_next_week_bounds_after_current():
    ref = datetime(2026, 5, 7, 14, 30, tzinfo=ZoneInfo("Europe/Paris"))
    s, _ = next_week_bounds(ref, "Europe/Paris")
    assert s.weekday() == 0
    assert s > ref


def test_iso_label():
    s = datetime(2026, 5, 4, tzinfo=ZoneInfo("Europe/Paris"))  # Mon
    assert iso_label(s) == "2026-W19"


def test_iter_days():
    s = datetime(2026, 5, 4, tzinfo=ZoneInfo("Europe/Paris"))
    e = datetime(2026, 5, 11, tzinfo=ZoneInfo("Europe/Paris"))
    days = list(iter_days(s, e))
    assert len(days) == 7
    assert days[0].isoformat() == "2026-05-04"
    assert days[-1].isoformat() == "2026-05-10"


def test_parse_hhmm():
    t = parse_hhmm("08:30")
    assert t.hour == 8 and t.minute == 30

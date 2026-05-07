from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from weekly_brief.calendars import collect_events, free_slots, parse_calendar
from weekly_brief.config import AppConfig, CalendarConfig, IMAPConfig, SMTPConfig
from weekly_brief.models import Event

ICS_SAMPLE = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:fixed-1@test
SUMMARY:Standup
DTSTART;TZID=Europe/Paris:20260504T093000
DTEND;TZID=Europe/Paris:20260504T100000
END:VEVENT
BEGIN:VEVENT
UID:rec-1@test
SUMMARY:Daily sync
DTSTART;TZID=Europe/Paris:20260504T110000
DTEND;TZID=Europe/Paris:20260504T113000
RRULE:FREQ=DAILY;COUNT=5
END:VEVENT
END:VCALENDAR
"""


def test_parse_calendar_expands_recurrence():
    tz = ZoneInfo("Europe/Paris")
    s = datetime(2026, 5, 4, 0, 0, tzinfo=tz)
    e = datetime(2026, 5, 11, 0, 0, tzinfo=tz)
    cfg = CalendarConfig(name="Work", category="work", url="x")
    events = parse_calendar(ICS_SAMPLE, cfg, s, e, tz)
    titles = [ev.title for ev in events]
    assert titles.count("Standup") == 1
    assert titles.count("Daily sync") == 5
    for ev in events:
        assert ev.category == "work"


def test_free_slots_subtracts_busy():
    tz = ZoneInfo("Europe/Paris")
    s = datetime(2026, 5, 4, 0, 0, tzinfo=tz)
    e = datetime(2026, 5, 11, 0, 0, tzinfo=tz)
    busy = [
        Event(
            uid="x",
            start=datetime(2026, 5, 4, 9, 0, tzinfo=tz),
            end=datetime(2026, 5, 4, 10, 0, tzinfo=tz),
            title="Mtg",
            location="",
            attendees=[],
            organizer="",
            category="work",
            source_name="W",
            description="",
        )
    ]
    work_hours = {
        "monday": [["08:00", "12:00"]],
        "tuesday": [["08:00", "12:00"]],
        "wednesday": [["08:00", "12:00"]],
        "thursday": [["08:00", "12:00"]],
        "friday": [["08:00", "12:00"]],
    }
    out = free_slots(busy, s, e, work_hours, "Europe/Paris", min_minutes=30)
    mon = out["2026-05-04"]
    # 08-09 free + 10-12 free; the 09-10 busy block removed.
    assert len(mon) == 2
    assert mon[0].start.hour == 8 and mon[0].end.hour == 9
    assert mon[1].start.hour == 10 and mon[1].end.hour == 12
    # Saturday/Sunday no work hours -> empty.
    assert out["2026-05-09"] == []
    assert out["2026-05-10"] == []


def test_calendar_config_requires_url_or_urls():
    with pytest.raises(Exception):
        CalendarConfig(name="X", category="work")


def test_calendar_feeds_single_vs_multi():
    single = CalendarConfig(name="Work", category="work", url="u1")
    assert single.feeds() == [("Work", "u1")]

    multi = CalendarConfig(name="Work", category="work", urls=["u1", "u2", "u3"])
    feeds = multi.feeds()
    assert feeds == [("Work #1", "u1"), ("Work #2", "u2"), ("Work #3", "u3")]

    one_in_list = CalendarConfig(name="Work", category="work", urls=["only"])
    assert one_in_list.feeds() == [("Work", "only")]


def test_collect_events_iterates_all_feeds_per_category():
    tz = ZoneInfo("Europe/Paris")
    s = datetime(2026, 5, 4, 0, 0, tzinfo=tz)
    e = datetime(2026, 5, 11, 0, 0, tzinfo=tz)
    cfg = AppConfig(
        timezone="Europe/Paris",
        imap=IMAPConfig(host="x", user="u"),
        smtp=SMTPConfig(host="x", user="u", to="u"),
        calendars=[
            CalendarConfig(
                name="Work",
                category="work",
                urls=["https://a/main.ics", "https://a/team.ics"],
            ),
        ],
    )
    fetched: list[str] = []

    def _fake_fetch(url: str) -> bytes:
        fetched.append(url)
        return ICS_SAMPLE

    events = collect_events(cfg, s, e, fetch=_fake_fetch)
    # Two URLs each yielding 1 Standup + 5 daily syncs = 12 events.
    assert len(fetched) == 2
    assert len(events) == 12
    sources = {ev.source_name for ev in events}
    assert sources == {"Work #1", "Work #2"}
    assert all(ev.category == "work" for ev in events)


def test_free_slots_full_day_when_no_events():
    tz = ZoneInfo("Europe/Paris")
    s = datetime(2026, 5, 4, 0, 0, tzinfo=tz)
    e = datetime(2026, 5, 11, 0, 0, tzinfo=tz)
    work_hours = {"monday": [["08:00", "19:00"]]}
    out = free_slots([], s, e, work_hours, "Europe/Paris", min_minutes=30)
    assert len(out["2026-05-04"]) == 1
    assert out["2026-05-04"][0].duration_min == 11 * 60

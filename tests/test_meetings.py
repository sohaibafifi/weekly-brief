from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from weekly_brief.meetings import attach_threads_to_events
from weekly_brief.models import Event, Message, Thread


def _ev(attendees):
    tz = ZoneInfo("Europe/Paris")
    return Event(
        uid="e1",
        start=datetime(2026, 5, 4, 9, 0, tzinfo=tz),
        end=datetime(2026, 5, 4, 10, 0, tzinfo=tz),
        title="Sync",
        location="",
        attendees=attendees,
        organizer="me@x.com",
        category="work",
        source_name="Work",
        description="",
    )


def _msg(frm, to):
    return Message(
        uid="1",
        folder="INBOX",
        date=datetime(2026, 5, 1, tzinfo=timezone.utc),
        from_addr=frm,
        to_addrs=to,
        subject="re: sync",
        message_id="",
        in_reply_to="",
        references=[],
        flags=[],
        snippet="",
    )


def test_attach_threads_picks_overlap():
    ev = _ev(["alice@x.com", "bob@x.com"])
    t1 = Thread(subject="re: sync", messages=[_msg("alice@x.com", ["me@x.com"])])
    t2 = Thread(subject="other", messages=[_msg("nobody@y.com", ["other@y.com"])])
    attach_threads_to_events([ev], [t1, t2], top_k=3)
    assert len(ev.related_threads) == 1
    assert ev.related_threads[0].subject == "re: sync"

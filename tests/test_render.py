from datetime import datetime
from zoneinfo import ZoneInfo

from weekly_brief.models import Event, Slot
from weekly_brief.render import build_brief, render_html, render_markdown


def _ev(start_h, title, cat="work"):
    tz = ZoneInfo("Europe/Paris")
    s = datetime(2026, 5, 4, start_h, 0, tzinfo=tz)
    e = datetime(2026, 5, 4, start_h + 1, 0, tzinfo=tz)
    return Event(
        uid=f"ev{start_h}",
        start=s,
        end=e,
        title=title,
        location="Office",
        attendees=["a@x.com", "b@x.com"],
        organizer="me@x.com",
        category=cat,
        source_name="Work",
        description="x",
    )


def _make_brief(locale: str):
    tz = ZoneInfo("Europe/Paris")
    events = [_ev(9, "Standup"), _ev(14, "Review", cat="personal")]
    free = {
        "2026-05-04": [
            Slot(
                datetime(2026, 5, 4, 8, 0, tzinfo=tz),
                datetime(2026, 5, 4, 9, 0, tzinfo=tz),
            )
        ]
    }
    return build_brief(
        week_iso="2026-W19",
        week_start=datetime(2026, 5, 4, tzinfo=tz),
        week_end=datetime(2026, 5, 11, tzinfo=tz),
        timezone="Europe/Paris",
        events=events,
        free_slots_by_day=free,
        flagged=[],
        vip=[],
        awaiting=[],
        narrative="Calm week with two anchors.",
        locale=locale,
    )


def test_render_html_and_md_english():
    brief = _make_brief("en")
    html = render_html(brief)
    md = render_markdown(brief)
    assert "Weekly Brief" in html
    assert "Standup" in html
    assert "Standup" in md
    assert "Free slots" in md


def test_render_html_and_md_french():
    brief = _make_brief("fr")
    html = render_html(brief)
    md = render_markdown(brief)
    assert "Brief hebdomadaire" in html
    assert "Mails à traiter" in html
    assert "Personnel" in html
    assert "Disponibilités" in md
    assert "Aucun" in md or "Aucune" in md

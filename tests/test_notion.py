from datetime import datetime
from zoneinfo import ZoneInfo

import respx
from httpx import Response

from weekly_brief.config import NotionConfig
from weekly_brief.models import Event, Slot
from weekly_brief.notion import NotionClient, build_blocks
from weekly_brief.render import build_brief


def _brief(locale="fr"):
    tz = ZoneInfo("Europe/Paris")
    ev = Event(
        uid="e1",
        start=datetime(2026, 5, 11, 9, 30, tzinfo=tz),
        end=datetime(2026, 5, 11, 10, 30, tzinfo=tz),
        title="Standup",
        location="Office",
        attendees=["a@x.com"],
        organizer="me@x.com",
        category="work",
        source_name="Work",
        description="",
    )
    free = {
        "2026-05-11": [
            Slot(
                datetime(2026, 5, 11, 8, 0, tzinfo=tz),
                datetime(2026, 5, 11, 9, 0, tzinfo=tz),
            )
        ]
    }
    return build_brief(
        week_iso="2026-W20",
        week_start=datetime(2026, 5, 11, tzinfo=tz),
        week_end=datetime(2026, 5, 18, tzinfo=tz),
        timezone="Europe/Paris",
        events=[ev],
        free_slots_by_day=free,
        flagged=[],
        vip=[],
        awaiting=[],
        narrative="<p>Calme.</p>",
        locale=locale,
    )


def _flatten_text(block) -> str:
    """Collect all rich_text content from a block (incl. one level of children)."""
    out: list[str] = []
    btype = block.get("type", "")
    body = block.get(btype, {}) or {}
    for rt in body.get("rich_text", []) or []:
        out.append(rt.get("text", {}).get("content", ""))
    for child in body.get("children", []) or []:
        out.append(_flatten_text(child))
    return " | ".join(out)


def test_build_blocks_has_required_sections():
    blocks = build_blocks(_brief("fr"))
    types = [b["type"] for b in blocks]
    # New structure uses callouts, dividers, toggles + h2.
    assert "callout" in types
    assert "divider" in types
    assert "heading_2" in types

    callouts = [_flatten_text(b) for b in blocks if b["type"] == "callout"]
    assert any("La semaine à venir" in c for c in callouts)
    assert any("En attente de réponse" in c for c in callouts)
    assert any("Suivis" in c for c in callouts)
    assert any("Contacts prioritaires" in c for c in callouts)

    headings = [_flatten_text(b) for b in blocks if b["type"] == "heading_2"]
    assert any("Événements par catégorie" in h for h in headings)
    assert any("Disponibilités" in h for h in headings)
    assert any("Mails à traiter" in h for h in headings)

    # Event bullet present (rich_text segments concatenated).
    bullets = [_flatten_text(b) for b in blocks if b["type"] == "bulleted_list_item"]
    assert any("Standup" in s for s in bullets)


def test_build_blocks_uses_locale_dates():
    blocks = build_blocks(_brief("fr"))
    bullets = [_flatten_text(b) for b in blocks if b["type"] == "bulleted_list_item"]
    # French abbreviated weekday for 2026-05-11 (Monday) = "lun."
    assert any("lun." in s for s in bullets)


def test_build_blocks_english():
    blocks = build_blocks(_brief("en"))
    headings = [_flatten_text(b) for b in blocks if b["type"] == "heading_2"]
    assert any("Events by category" in h for h in headings)
    callouts = [_flatten_text(b) for b in blocks if b["type"] == "callout"]
    assert any("Week ahead" in c for c in callouts)


def test_category_color_applied():
    blocks = build_blocks(_brief("fr"))
    h3s = [b for b in blocks if b["type"] == "heading_3"]
    # work category should have blue color on its h3.
    assert any(b["heading_3"].get("color") == "blue" for b in h3s)


def test_disabled_when_missing_creds(monkeypatch):
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    cfg = NotionConfig(enabled=True, database_id="abc")
    assert NotionClient(cfg).enabled is False
    cfg2 = NotionConfig(enabled=False)
    monkeypatch.setenv("NOTION_API_KEY", "x")
    assert NotionClient(cfg2).enabled is False


@respx.mock
def test_publish_creates_when_no_existing(monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", "secret-token")
    cfg = NotionConfig(enabled=True, database_id="db123")
    client = NotionClient(cfg)
    assert client.enabled

    respx.post("https://api.notion.com/v1/databases/db123/query").mock(
        return_value=Response(200, json={"results": [], "has_more": False})
    )
    create_route = respx.post("https://api.notion.com/v1/pages").mock(
        return_value=Response(200, json={"id": "newpage-1"})
    )

    page_id = client.publish(_brief("fr"))
    assert page_id == "newpage-1"
    assert create_route.called
    body = create_route.calls.last.request.read()
    assert b"db123" in body
    assert b"Brief 2026-W20" in body
    # Summary property carries narrative text (HTML stripped).
    assert b"Summary" in body
    assert b"Calme." in body
    assert b"<p>" not in body


@respx.mock
def test_publish_skips_summary_when_disabled(monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", "secret-token")
    cfg = NotionConfig(enabled=True, database_id="db123", summary_prop="")
    client = NotionClient(cfg)

    respx.post("https://api.notion.com/v1/databases/db123/query").mock(
        return_value=Response(200, json={"results": [], "has_more": False})
    )
    create_route = respx.post("https://api.notion.com/v1/pages").mock(
        return_value=Response(200, json={"id": "newpage-2"})
    )
    client.publish(_brief("fr"))
    body = create_route.calls.last.request.read()
    assert b'"Summary"' not in body


@respx.mock
def test_publish_archives_existing_then_creates_new(monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", "secret-token")
    cfg = NotionConfig(enabled=True, database_id="db123")
    client = NotionClient(cfg)

    respx.post("https://api.notion.com/v1/databases/db123/query").mock(
        return_value=Response(200, json={"results": [{"id": "old-page"}], "has_more": False})
    )
    archive_route = respx.patch("https://api.notion.com/v1/pages/old-page").mock(
        return_value=Response(200, json={"id": "old-page", "archived": True})
    )
    create_route = respx.post("https://api.notion.com/v1/pages").mock(
        return_value=Response(200, json={"id": "fresh-page"})
    )

    page_id = client.publish(_brief("fr"))
    assert page_id == "fresh-page"
    # Old page archived (single PATCH with archived=true).
    assert archive_route.called
    archive_body = archive_route.calls.last.request.read()
    assert b'"archived": true' in archive_body or b'"archived":true' in archive_body
    # New page created.
    assert create_route.called
    # No per-block delete calls were made.
    delete_calls = [c for c in respx.calls if c.request.method == "DELETE"]
    assert delete_calls == []

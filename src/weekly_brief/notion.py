"""Notion REST integration: publish weekly brief as DB row + styled page blocks."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from babel.dates import format_date as babel_format_date
from babel.dates import format_datetime as babel_format_datetime

from weekly_brief.config import NotionConfig
from weekly_brief.render import Brief
from weekly_brief.textutil import fmt_hours, html_to_text

log = logging.getLogger(__name__)

NOTION_TEXT_LIMIT = 2000  # per rich_text chunk

# Category presentation: emoji + Notion text/background color name.
CATEGORY_STYLE: dict[str, tuple[str, str]] = {
    "work": ("💼", "blue"),
    "personal": ("🌿", "green"),
    "family": ("👨‍👩‍👧", "yellow"),
    "other": ("📌", "purple"),
}


def _txt(s: str, bold: bool = False, color: str = "default") -> list[dict[str, Any]]:
    s = (s or "")[:NOTION_TEXT_LIMIT]
    if not s:
        return []
    annotations = {"bold": bold} if bold else {}
    rt: dict[str, Any] = {"type": "text", "text": {"content": s}}
    if annotations:
        rt["annotations"] = annotations
    if color != "default":
        rt.setdefault("annotations", {})["color"] = color
    return [rt]


def _rich(parts: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Build rich_text from segments. Each part = (text, annotations_dict)."""
    out: list[dict[str, Any]] = []
    for content, ann in parts:
        if not content:
            continue
        seg: dict[str, Any] = {"type": "text", "text": {"content": content[:NOTION_TEXT_LIMIT]}}
        if ann:
            seg["annotations"] = ann
        out.append(seg)
    return out


def _para(s: str, color: str = "default") -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _txt(s), "color": color},
    }


def _h2(s: str, color: str = "default") -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": _txt(s), "color": color},
    }


def _h3(s: str, color: str = "default") -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {"rich_text": _txt(s), "color": color},
    }


def _bul(rich: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": rich},
    }


def _divider() -> dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def _callout(text: str, emoji: str, color: str = "default") -> dict[str, Any]:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _txt(text),
            "icon": {"type": "emoji", "emoji": emoji},
            "color": color,
        },
    }


def _callout_with_children(
    text: str, emoji: str, color: str, children: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _txt(text),
            "icon": {"type": "emoji", "emoji": emoji},
            "color": color,
            "children": children,
        },
    }


def _toggle(text: str, children: list[dict[str, Any]], color: str = "default") -> dict[str, Any]:
    return {
        "object": "block",
        "type": "toggle",
        "toggle": {"rich_text": _txt(text), "color": color, "children": children},
    }


def _labels(locale: str) -> dict[str, str]:
    if locale == "fr":
        return {
            "header": "Brief hebdomadaire",
            "narrative": "La semaine à venir",
            "events": "Événements par catégorie",
            "free": "Disponibilités",
            "mail": "Mails à traiter",
            "awaiting": "En attente de réponse",
            "flagged": "Suivis",
            "vip": "Contacts prioritaires",
            "no_subj": "(sans objet)",
            "no_events": "Aucun événement.",
            "no_free": "Pas de créneau libre.",
            "none": "Aucun.",
            "from": "de",
        }
    return {
        "header": "Weekly brief",
        "narrative": "Week ahead",
        "events": "Events by category",
        "free": "Free slots",
        "mail": "Mail needs attention",
        "awaiting": "Awaiting reply",
        "flagged": "Flagged",
        "vip": "VIPs",
        "no_subj": "(no subject)",
        "no_events": "No events.",
        "no_free": "No free slots.",
        "none": "None.",
        "from": "from",
    }


def _fmt_dt(dt: datetime, locale: str, tz: ZoneInfo, pattern: str = "EEE d MMM HH:mm") -> str:
    return babel_format_datetime(dt.astimezone(tz), pattern, locale=locale)


def _fmt_time(dt: datetime, locale: str, tz: ZoneInfo) -> str:
    return babel_format_datetime(dt.astimezone(tz), "HH:mm", locale=locale)


def _fmt_day(iso: str, locale: str) -> str:
    from datetime import date as _date

    return babel_format_date(_date.fromisoformat(iso), "EEEE d MMM", locale=locale).capitalize()


def build_blocks(brief: Brief) -> list[dict[str, Any]]:
    """Convert Brief view-model into a styled Notion block list."""
    L = _labels(brief.locale)
    locale = brief.locale
    tz = ZoneInfo(brief.timezone)
    blocks: list[dict[str, Any]] = []

    # Header banner: week range, locale-aware.
    range_label = (
        f"{babel_format_date(brief.week_start.date(), 'EEEE d MMMM y', locale=locale)} → "
        f"{babel_format_date((brief.week_end).date(), 'EEEE d MMMM y', locale=locale)}"
    )
    blocks.append(_callout(range_label, "📅", "blue_background"))

    # Narrative as a quote block (visually distinct, no extra heading).
    if brief.narrative:
        plain = html_to_text(brief.narrative)
        children: list[dict[str, Any]] = []
        for para in [c.strip() for c in plain.split("\n\n") if c.strip()]:
            children.append(_para(para))
        blocks.append(_callout_with_children(L["narrative"], "✨", "gray_background", children))

    blocks.append(_divider())

    # Events by category, color-coded heading.
    blocks.append(_h2(f"📂 {L['events']}"))
    if not brief.events_by_category:
        blocks.append(_para(L["no_events"], color="gray"))
    else:
        for cat, evs in brief.events_by_category.items():
            emoji, color = CATEGORY_STYLE.get(cat, CATEGORY_STYLE["other"])
            cat_title = f"{emoji}  {cat.capitalize()} ({len(evs)})"
            blocks.append(_h3(cat_title, color=color))
            for ev in evs:
                stamp = _fmt_dt(ev.start, locale, tz)
                segs: list[tuple[str, dict[str, Any]]] = [
                    (f"{stamp}", {"bold": True}),
                    (f"  {ev.title}", {}),
                ]
                if ev.location:
                    segs.append((f"  ·  {ev.location}", {"color": "gray"}))
                blocks.append(_bul(_rich(segs)))

    blocks.append(_divider())

    # Free slots: one toggle per day with bullets inside.
    blocks.append(_h2(f"🟢 {L['free']}"))
    any_free = False
    for day, slots in brief.free_slots_by_day.items():
        if not slots:
            continue
        any_free = True
        day_label = _fmt_day(day, locale)
        children: list[dict[str, Any]] = []
        for s in slots:
            line = (
                f"{_fmt_time(s.start, locale, tz)} – {_fmt_time(s.end, locale, tz)}"
                f"  ({fmt_hours(s.duration_min)})"
            )
            children.append(_bul(_rich([(line, {"color": "green"})])))
        summary = f"{day_label}  ·  {len(slots)}"
        blocks.append(_toggle(summary, children, color="default"))
    if not any_free:
        blocks.append(_para(L["no_free"], color="gray"))

    blocks.append(_divider())

    # Mail attention: each bucket as a coloured callout with bullet children.
    blocks.append(_h2(f"✉️ {L['mail']}"))
    awaiting = brief.mail_attention.get("awaiting_reply", []) or []
    flagged = brief.mail_attention.get("flagged", []) or []
    vip = brief.mail_attention.get("vip", []) or []

    def _mail_bullets(items, getter_subj, getter_from, label_from: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not items:
            out.append(_para(L["none"], color="gray"))
            return out
        for it in items:
            subj = getter_subj(it) or L["no_subj"]
            sender = getter_from(it)
            segs = [
                (subj, {"bold": True}),
                (f"  ·  {label_from} {sender}", {"color": "gray"}),
            ]
            out.append(_bul(_rich(segs)))
        return out

    blocks.append(
        _callout_with_children(
            f"{L['awaiting']} · {len(awaiting)}",
            "📨",
            "red_background",
            _mail_bullets(
                awaiting, lambda t: t.subject, lambda t: t.last_inbound_from, L["from"]
            ),
        )
    )
    blocks.append(
        _callout_with_children(
            f"{L['flagged']} · {len(flagged)}",
            "🚩",
            "yellow_background",
            _mail_bullets(flagged, lambda m: m.subject, lambda m: m.from_addr, L["from"]),
        )
    )
    blocks.append(
        _callout_with_children(
            f"{L['vip']} · {len(vip)}",
            "⭐",
            "purple_background",
            _mail_bullets(vip, lambda m: m.subject, lambda m: m.from_addr, L["from"]),
        )
    )

    return blocks


class NotionClient:
    def __init__(self, cfg: NotionConfig):
        self.cfg = cfg

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.enabled and self.cfg.api_key and self.cfg.database_id)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Notion-Version": self.cfg.notion_version,
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.cfg.base_url.rstrip('/')}{path}"

    def _post(self, path: str, payload: dict) -> dict:
        r = httpx.post(self._url(path), headers=self._headers(), json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, payload: dict) -> dict:
        r = httpx.patch(self._url(path), headers=self._headers(), json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def find_page_by_title(self, title: str) -> str | None:
        data = self._post(
            f"/databases/{self.cfg.database_id}/query",
            {
                "filter": {
                    "property": self.cfg.title_prop,
                    "title": {"equals": title},
                },
                "page_size": 1,
            },
        )
        results = data.get("results", [])
        return results[0]["id"] if results else None

    def append_blocks(self, page_id: str, blocks: list[dict]) -> None:
        for i in range(0, len(blocks), 100):
            self._patch(f"/blocks/{page_id}/children", {"children": blocks[i : i + 100]})

    def _properties(self, brief: Brief, title: str, attachment_url: str | None) -> dict:
        props: dict[str, Any] = {
            self.cfg.title_prop: {
                "title": [{"type": "text", "text": {"content": title}}],
            },
        }
        if self.cfg.week_prop:
            props[self.cfg.week_prop] = {
                "date": {
                    "start": brief.week_start.date().isoformat(),
                    "end": (brief.week_end.date()).isoformat(),
                },
            }
        if self.cfg.summary_prop and brief.narrative:
            summary = html_to_text(brief.narrative)[:NOTION_TEXT_LIMIT]
            props[self.cfg.summary_prop] = {
                "rich_text": [{"type": "text", "text": {"content": summary}}],
            }
        if self.cfg.url_prop and attachment_url:
            props[self.cfg.url_prop] = {"url": attachment_url}
        return props

    def publish(self, brief: Brief, attachment_url: str | None = None) -> str:
        """Publish `brief` as a fresh DB row. If a row with the same title already
        exists, archive it (soft-delete to trash, recoverable 30d) and create a new one.
        Two API calls in the common path — much faster than per-block deletion."""
        title = f"Brief {brief.week_iso}"
        props = self._properties(brief, title, attachment_url)
        blocks = build_blocks(brief)

        existing = self.find_page_by_title(title)
        if existing:
            log.info("Notion: archiving previous page %s", existing)
            try:
                self._patch(f"/pages/{existing}", {"archived": True})
            except Exception as exc:
                log.warning("Could not archive old page %s: %s", existing, exc)

        log.info("Notion: creating new page in DB %s", self.cfg.database_id)
        page = self._post(
            "/pages",
            {
                "parent": {"database_id": self.cfg.database_id},
                "properties": props,
                "children": blocks[:100],
            },
        )
        page_id = page["id"]
        if len(blocks) > 100:
            self.append_blocks(page_id, blocks[100:])
        return page_id

"""End-to-end pipeline: fetch → analyze → enrich → render → store/send."""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from weekly_brief.calendars import collect_events, free_slots
from weekly_brief.config import AppConfig
from weekly_brief.llm import MistralClient
from weekly_brief.mail import MailClient
from weekly_brief.meetings import attach_threads_to_events
from weekly_brief.models import Event
from weekly_brief.notify import send_email
from weekly_brief.notion import NotionClient
from weekly_brief.render import build_brief, render_html, render_markdown
from weekly_brief.store import write_outputs
from weekly_brief.textutil import html_to_text
from weekly_brief.threads import build_threads, filter_awaiting, mark_awaiting_reply
from weekly_brief.timeutil import iso_label, next_week_bounds, now_in, week_bounds

log = logging.getLogger(__name__)


def _summarize_for_llm(events: list[Event], free_by_day: dict) -> dict:
    return {
        "events": [
            {
                "title": ev.title,
                "start": ev.start.isoformat(),
                "end": ev.end.isoformat(),
                "category": ev.category,
                "attendees": ev.attendees[:5],
                "location": ev.location,
            }
            for ev in events
        ],
        "free_slots_by_day": {
            d: [{"start": s.start.isoformat(), "end": s.end.isoformat()} for s in slots]
            for d, slots in free_by_day.items()
        },
    }


def run_pipeline(cfg: AppConfig, send: bool = True, week: str = "next") -> Path:
    """Run full pipeline. `week`: 'next' (coming Mon) or 'current'."""
    ref = now_in(cfg.timezone)
    ws, we = week_bounds(ref, cfg.timezone) if week == "current" else next_week_bounds(ref, cfg.timezone)

    events = collect_events(cfg, ws, we)
    free_by_day = free_slots(events, ws, we, cfg.work_hours, cfg.timezone)

    flagged: list = []
    vip: list = []
    awaiting: list = []
    all_threads: list = []
    mc = MailClient(cfg)
    if cfg.mail_rules.flagged:
        flagged = mc.fetch_flagged(cfg.mail_rules.flagged_lookback_days)
    if cfg.mail_rules.vip:
        vip = mc.fetch_vip(cfg.mail_rules.vip_lookback_days)
    if cfg.mail_rules.awaiting_reply:
        inbound = mc.fetch_inbound(cfg.mail_rules.awaiting_reply_lookback_days)
        sent_msgs = mc.fetch_sent(cfg.mail_rules.awaiting_reply_lookback_days)
        all_threads = mark_awaiting_reply(build_threads(inbound, sent_msgs), cfg.imap.user)
        awaiting = filter_awaiting(all_threads)
    events = attach_threads_to_events(events, all_threads, top_k=3)

    llm = MistralClient(cfg.llm)
    narrative = llm.week_narrative(_summarize_for_llm(events, free_by_day), locale=cfg.locale)
    prep = llm.per_meeting_prep(events, locale=cfg.locale)
    for ev in events:
        if ev.uid in prep:
            ev.prep_notes = prep[ev.uid].get("prep_notes", "")
            ev.prep_questions = prep[ev.uid].get("questions_to_prepare", [])

    brief = build_brief(
        week_iso=iso_label(ws),
        week_start=ws,
        week_end=we,
        timezone=cfg.timezone,
        events=events,
        free_slots_by_day=free_by_day,
        flagged=flagged,
        vip=vip,
        awaiting=awaiting,
        narrative=narrative,
        locale=cfg.locale,
    )

    html = render_html(brief)
    markdown = render_markdown(brief)
    raw = {
        "week_iso": brief.week_iso,
        "week_start": brief.week_start.isoformat(),
        "week_end": brief.week_end.isoformat(),
        "timezone": brief.timezone,
        "events": [asdict(e) for e in events],
        "free_slots_by_day": {d: [asdict(s) for s in slots] for d, slots in free_by_day.items()},
        "narrative": narrative,
        "generated_at": datetime.now().isoformat(),
    }
    week_dir = write_outputs(cfg.output_dir, brief.week_iso, html, markdown, raw)

    notion = NotionClient(cfg.notion)
    if notion.enabled:
        notion.publish(brief)

    if send:
        is_fr = cfg.locale == "fr"
        prefix = "Brief hebdomadaire" if is_fr else "Weekly brief"
        subject = (
            f"{prefix} — {brief.week_iso} "
            f"{brief.week_start.strftime('%Y-%m-%d')}…{brief.week_end.strftime('%Y-%m-%d')}"
        )
        abstract = html_to_text(narrative) if narrative else ""
        attach_note = (
            "Détails complets dans la pièce jointe HTML."
            if is_fr
            else "Full details in the attached HTML file."
        )
        body = f"{abstract}\n\n— {attach_note}\n" if abstract else f"{attach_note}\n"
        send_email(
            cfg,
            subject,
            body,
            html_attachment=html,
            html_filename=f"weekly-brief-{brief.week_iso}.html",
        )

    return week_dir

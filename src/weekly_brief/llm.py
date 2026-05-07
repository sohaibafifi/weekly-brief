"""Mistral chat client + prompts for narrative + per-meeting prep."""
from __future__ import annotations

import json
import logging

import httpx

from weekly_brief.config import LLMConfig
from weekly_brief.models import Event

log = logging.getLogger(__name__)

NARRATIVE_SYSTEM = (
    "You are a concise executive assistant. Write the user's week-ahead overview "
    "in the user's locale (fr=French, en=English). ≤120 words. No headers, no bullets, plain text. "
    "Tone: calm, direct. Reference key events and free time. Never invent facts. "
    "If locale=fr, write entirely in French."
)

PREP_SYSTEM = (
    "You are a concise executive assistant preparing a busy professional for upcoming meetings. "
    "For each meeting return: prep_notes (≤80 words, plain text) and questions_to_prepare (3-5 short bullets). "
    "Base ONLY on provided context. Be specific. Output JSON exactly matching the schema. "
    "Respect the user's locale (fr=French, en=English). If locale=fr, write all prose in French."
)


class MistralClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.api_key)

    def _post(self, payload: dict, timeout: float = 60.0) -> dict:
        url = f"{self.cfg.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }
        r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()

    def ping(self) -> str:
        if not self.enabled:
            raise RuntimeError("Mistral API key missing")
        data = self._post(
            {
                "model": self.cfg.model,
                "messages": [{"role": "user", "content": "say 'ok'"}],
                "max_tokens": 5,
                "temperature": 0,
            }
        )
        return data["choices"][0]["message"]["content"]

    def week_narrative(self, summary: dict, locale: str = "en") -> str:
        if not (self.enabled and self.cfg.features.week_narrative):
            return ""
        try:
            data = self._post(
                {
                    "model": self.cfg.model,
                    "messages": [
                        {"role": "system", "content": NARRATIVE_SYSTEM},
                        {
                            "role": "user",
                            "content": (
                                f"Locale: {locale}\nWeek summary JSON:\n"
                                + json.dumps(summary, ensure_ascii=False, default=str)
                            ),
                        },
                    ],
                    "max_tokens": 350,
                    "temperature": 0.4,
                }
            )
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            log.warning("Narrative LLM call failed: %s", exc)
            return ""

    def per_meeting_prep(self, events: list[Event], locale: str = "en") -> dict[str, dict]:
        if not (self.enabled and self.cfg.features.per_meeting_prep):
            return {}
        meetings = []
        for ev in events:
            if not ev.attendees:
                continue
            meetings.append(
                {
                    "uid": ev.uid,
                    "title": ev.title,
                    "start": ev.start.isoformat(),
                    "attendees": ev.attendees,
                    "description": ev.description[:600],
                    "location": ev.location,
                    "related_threads": [
                        {
                            "subject": t.subject,
                            "last_date": t.last_date.isoformat(),
                            "snippets": [m.snippet for m in t.messages[-3:]],
                        }
                        for t in ev.related_threads
                    ],
                }
            )
        if not meetings:
            return {}
        try:
            data = self._post(
                {
                    "model": self.cfg.model,
                    "messages": [
                        {"role": "system", "content": PREP_SYSTEM},
                        {
                            "role": "user",
                            "content": (
                                f"Locale: {locale}\nReturn JSON: "
                                '{"meetings":[{"uid":..., "prep_notes":..., "questions_to_prepare":[...]}]} '
                                "for these meetings:\n"
                                + json.dumps(meetings, ensure_ascii=False, default=str)
                            ),
                        },
                    ],
                    "max_tokens": 1500,
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                }
            )
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            out: dict[str, dict] = {}
            for m in parsed.get("meetings", []):
                uid = m.get("uid")
                if not uid:
                    continue
                out[uid] = {
                    "prep_notes": (m.get("prep_notes") or "").strip(),
                    "questions_to_prepare": list(m.get("questions_to_prepare") or []),
                }
            return out
        except Exception as exc:
            log.warning("Prep LLM call failed: %s", exc)
            return {}

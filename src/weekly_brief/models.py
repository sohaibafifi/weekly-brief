"""Shared dataclasses used across modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Event:
    uid: str
    start: datetime
    end: datetime
    title: str
    location: str
    attendees: list[str]
    organizer: str
    category: str
    source_name: str
    description: str
    all_day: bool = False
    related_threads: list["Thread"] = field(default_factory=list)
    prep_notes: str = ""
    prep_questions: list[str] = field(default_factory=list)


@dataclass
class Slot:
    start: datetime
    end: datetime

    @property
    def duration_min(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass
class Message:
    uid: str
    folder: str
    date: datetime
    from_addr: str
    to_addrs: list[str]
    subject: str
    message_id: str
    in_reply_to: str
    references: list[str]
    flags: list[str]
    snippet: str

    @property
    def is_flagged(self) -> bool:
        return any(f.lower() in {"\\flagged", "flagged"} for f in self.flags)


@dataclass
class Thread:
    subject: str
    messages: list[Message]
    last_inbound_from: str = ""
    awaits_me: bool = False

    @property
    def last_date(self) -> datetime:
        return max(m.date for m in self.messages)

    @property
    def participants(self) -> set[str]:
        out: set[str] = set()
        for m in self.messages:
            if m.from_addr:
                out.add(m.from_addr.lower())
            for a in m.to_addrs:
                if a:
                    out.add(a.lower())
        return out

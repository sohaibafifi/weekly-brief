"""Group messages into threads + detect 'awaiting my reply'."""
from __future__ import annotations

import re
from collections import defaultdict

from weekly_brief.models import Message, Thread

_REPLY_PREFIX = re.compile(r"^\s*(re|fw|fwd|tr|aw|sv|res|antw)(\[\d+\])?:\s*", re.IGNORECASE)


def _norm_subject(s: str) -> str:
    prev = None
    out = s or ""
    while out != prev:
        prev = out
        out = _REPLY_PREFIX.sub("", out)
    return out.strip().lower()


def _thread_key(m: Message, id_to_root: dict[str, str]) -> str:
    """Use Message-ID chain root if available, else normalized subject."""
    if m.in_reply_to and m.in_reply_to in id_to_root:
        return id_to_root[m.in_reply_to]
    for r in m.references:
        if r in id_to_root:
            return id_to_root[r]
    return f"subj::{_norm_subject(m.subject)}"


def build_threads(inbound: list[Message], sent: list[Message]) -> list[Thread]:
    all_msgs = sorted(inbound + sent, key=lambda m: m.date)
    id_to_root: dict[str, str] = {}
    groups: dict[str, list[Message]] = defaultdict(list)

    for m in all_msgs:
        key = _thread_key(m, id_to_root)
        groups[key].append(m)
        if m.message_id:
            id_to_root[m.message_id] = key

    threads: list[Thread] = []
    for _, msgs in groups.items():
        msgs.sort(key=lambda x: x.date)
        threads.append(Thread(subject=msgs[-1].subject, messages=msgs))
    return threads


def mark_awaiting_reply(threads: list[Thread], my_address: str) -> list[Thread]:
    """A thread awaits me iff last message is inbound (folder=INBOX) and no later sent reply."""
    me = my_address.lower()
    out: list[Thread] = []
    for t in threads:
        last = t.messages[-1]
        is_last_inbound = last.folder.lower() != "sent" and me not in {last.from_addr}
        if is_last_inbound:
            t.awaits_me = True
            t.last_inbound_from = last.from_addr
        out.append(t)
    return out


def filter_awaiting(threads: list[Thread]) -> list[Thread]:
    return sorted([t for t in threads if t.awaits_me], key=lambda t: t.last_date)

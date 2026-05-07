"""IMAP fetching for flagged + VIP + thread analysis."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses

from imap_tools import AND, MailBox, MailMessage

from weekly_brief.config import AppConfig
from weekly_brief.models import Message
from weekly_brief.timeutil import now_in

log = logging.getLogger(__name__)


def _addrs(headers) -> list[str]:
    if headers is None:
        return []
    if isinstance(headers, str):
        pairs = getaddresses([headers])
    elif isinstance(headers, (list, tuple)):
        pairs = getaddresses(list(headers))
    else:
        pairs = []
    return [a.lower() for _, a in pairs if a]


def _refs(value: str | None) -> list[str]:
    if not value:
        return []
    return [t.strip() for t in value.replace("\n", " ").split() if t.strip()]


def _to_msg(m: MailMessage, folder: str) -> Message:
    msg_id = (m.headers.get("message-id", ("",)) or ("",))[0]
    in_reply = (m.headers.get("in-reply-to", ("",)) or ("",))[0]
    refs = (m.headers.get("references", ("",)) or ("",))[0]
    snippet = (m.text or m.html or "").strip().replace("\n", " ")[:300]
    return Message(
        uid=str(m.uid or ""),
        folder=folder,
        date=m.date or datetime.now(timezone.utc),
        from_addr=(m.from_ or "").lower(),
        to_addrs=_addrs(m.to) + _addrs(m.cc),
        subject=m.subject or "",
        message_id=msg_id.strip("<>") if msg_id else "",
        in_reply_to=in_reply.strip("<>") if in_reply else "",
        references=[r.strip("<>") for r in _refs(refs)],
        flags=list(m.flags or []),
        snippet=snippet,
    )


class MailClient:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg

    def _open(self) -> MailBox:
        box = MailBox(self.cfg.imap.host, port=self.cfg.imap.port)
        box.login(self.cfg.imap.user, self.cfg.imap.password)
        return box

    def fetch_flagged(self, days: int) -> list[Message]:
        since = (now_in(self.cfg.timezone) - timedelta(days=days)).date()
        out: list[Message] = []
        with self._open() as box:
            box.folder.set(self.cfg.imap.inbox)
            for m in box.fetch(AND(flagged=True, date_gte=since), mark_seen=False, bulk=True):
                out.append(_to_msg(m, self.cfg.imap.inbox))
        return out

    def fetch_vip(self, days: int) -> list[Message]:
        since = (now_in(self.cfg.timezone) - timedelta(days=days)).date()
        out: list[Message] = []
        emails = self.cfg.vip_emails
        domains = self.cfg.vip_domains
        with self._open() as box:
            box.folder.set(self.cfg.imap.inbox)
            for m in box.fetch(AND(date_gte=since), mark_seen=False, bulk=True, limit=2000):
                sender = (m.from_ or "").lower()
                if sender in emails or any(sender.endswith("@" + d) for d in domains):
                    out.append(_to_msg(m, self.cfg.imap.inbox))
        return out

    def fetch_inbound(self, days: int) -> list[Message]:
        since = (now_in(self.cfg.timezone) - timedelta(days=days)).date()
        out: list[Message] = []
        with self._open() as box:
            box.folder.set(self.cfg.imap.inbox)
            for m in box.fetch(AND(date_gte=since), mark_seen=False, bulk=True, limit=2000):
                out.append(_to_msg(m, self.cfg.imap.inbox))
        return out

    def fetch_sent(self, days: int) -> list[Message]:
        since = (now_in(self.cfg.timezone) - timedelta(days=days)).date()
        out: list[Message] = []
        with self._open() as box:
            try:
                box.folder.set(self.cfg.imap.sent)
            except Exception as exc:
                log.warning("Sent folder %r unavailable: %s", self.cfg.imap.sent, exc)
                return out
            for m in box.fetch(AND(date_gte=since), mark_seen=False, bulk=True, limit=2000):
                out.append(_to_msg(m, self.cfg.imap.sent))
        return out

    def ping(self) -> dict[str, int]:
        with self._open() as box:
            box.folder.set(self.cfg.imap.inbox)
            count = sum(1 for _ in box.fetch(AND(all=True), mark_seen=False, bulk=True, limit=1))
        return {"inbox_reachable": count}

"""Shared text helpers."""
from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")


def fmt_hours(minutes: int) -> str:
    """Format minutes as hours: 60→'1 h', 90→'1h30', 30→'30 min'."""
    minutes = int(minutes or 0)
    h, m = divmod(minutes, 60)
    if h == 0:
        return f"{m} min"
    if m == 0:
        return f"{h} h"
    return f"{h}h{m:02d}"


def html_to_text(s: str) -> str:
    """Best-effort HTML → plain-text. Preserves block breaks + bullets."""
    if not s:
        return s
    s = re.sub(r"</(p|h[1-6]|li|div|tr)>|<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<li[^>]*>", "- ", s, flags=re.IGNORECASE)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()

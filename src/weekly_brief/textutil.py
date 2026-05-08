"""Shared text helpers."""
from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(s: str) -> str:
    """Best-effort HTML → plain-text. Preserves block breaks + bullets."""
    if not s:
        return s
    s = re.sub(r"</(p|h[1-6]|li|div|tr)>|<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<li[^>]*>", "- ", s, flags=re.IGNORECASE)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()

"""Write outputs (HTML/Markdown/JSON) under output_dir/<iso-week>/, refresh latest symlink."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


def _default(o):
    if is_dataclass(o) and not isinstance(o, type):
        return asdict(o)
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def write_outputs(
    output_dir: Path, week_iso: str, html: str, markdown: str, raw: dict | None = None
) -> Path:
    output_dir = output_dir.expanduser()
    week_dir = output_dir / week_iso
    week_dir.mkdir(parents=True, exist_ok=True)
    (week_dir / "index.html").write_text(html, encoding="utf-8")
    (week_dir / "brief.md").write_text(markdown, encoding="utf-8")
    if raw is not None:
        (week_dir / "raw.json").write_text(
            json.dumps(raw, default=_default, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    latest = output_dir / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(week_dir, target_is_directory=True)
    except OSError as exc:
        log.warning("Could not refresh latest symlink: %s", exc)
    return week_dir

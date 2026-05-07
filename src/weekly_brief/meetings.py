"""Link calendar events to recent mail threads via attendees."""
from __future__ import annotations

from weekly_brief.models import Event, Thread


def attach_threads_to_events(
    events: list[Event], threads: list[Thread], top_k: int = 3
) -> list[Event]:
    for ev in events:
        if not ev.attendees:
            continue
        attendees = {a.lower() for a in ev.attendees if a}
        if not attendees:
            continue
        scored: list[tuple[float, Thread]] = []
        for t in threads:
            if attendees & t.participants:
                # weight: number of attendees overlap × recency
                overlap = len(attendees & t.participants)
                scored.append((overlap, t))
        scored.sort(key=lambda x: (x[0], x[1].last_date), reverse=True)
        ev.related_threads = [t for _, t in scored[:top_k]]
    return events

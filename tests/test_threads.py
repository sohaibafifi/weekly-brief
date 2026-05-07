from datetime import datetime, timezone

from weekly_brief.models import Message
from weekly_brief.threads import (
    _norm_subject,
    build_threads,
    filter_awaiting,
    mark_awaiting_reply,
)


def _msg(uid, folder, days_ago, frm, to, subject, mid="", in_reply="", refs=()):
    return Message(
        uid=uid,
        folder=folder,
        date=datetime(2026, 5, 1 + days_ago, 12, 0, tzinfo=timezone.utc),
        from_addr=frm.lower(),
        to_addrs=[t.lower() for t in to],
        subject=subject,
        message_id=mid,
        in_reply_to=in_reply,
        references=list(refs),
        flags=[],
        snippet="",
    )


def test_norm_subject_strips_replies():
    assert _norm_subject("Re: hello") == "hello"
    assert _norm_subject("RE: Fwd: TR: meeting") == "meeting"
    assert _norm_subject("AW[5]: status") == "status"


def test_thread_grouping_and_awaiting_when_last_inbound():
    me = "me@x.com"
    a = _msg("1", "INBOX", 0, "boss@x.com", [me], "Re: budget", mid="m1")
    b = _msg("2", "Sent", 1, me, ["boss@x.com"], "Re: budget", mid="m2", in_reply="m1")
    c = _msg("3", "INBOX", 2, "boss@x.com", [me], "Re: budget", mid="m3", in_reply="m2")
    threads = build_threads(inbound=[a, c], sent=[b])
    assert len(threads) == 1
    threads = mark_awaiting_reply(threads, me)
    awaiting = filter_awaiting(threads)
    assert len(awaiting) == 1
    assert awaiting[0].last_inbound_from == "boss@x.com"


def test_no_awaiting_when_user_replied_last():
    me = "me@x.com"
    a = _msg("1", "INBOX", 0, "boss@x.com", [me], "ping", mid="m1")
    b = _msg("2", "Sent", 1, me, ["boss@x.com"], "Re: ping", mid="m2", in_reply="m1")
    threads = build_threads(inbound=[a], sent=[b])
    threads = mark_awaiting_reply(threads, me)
    assert filter_awaiting(threads) == []

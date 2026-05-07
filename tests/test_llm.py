import respx
from httpx import Response

from weekly_brief.config import LLMConfig
from weekly_brief.llm import MistralClient


def _client(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    return MistralClient(LLMConfig())


@respx.mock
def test_week_narrative(monkeypatch):
    client = _client(monkeypatch)
    respx.post("https://api.mistral.ai/v1/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": "Calm week."}}]})
    )
    out = client.week_narrative({"events": [], "free_slots_by_day": {}})
    assert out == "Calm week."


@respx.mock
def test_per_meeting_prep_parses_json(monkeypatch):
    client = _client(monkeypatch)
    respx.post("https://api.mistral.ai/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"meetings":[{"uid":"e1","prep_notes":"Bring slides",'
                                '"questions_to_prepare":["What is the goal?","Budget?"]}]}'
                            )
                        }
                    }
                ]
            },
        )
    )
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from weekly_brief.models import Event

    tz = ZoneInfo("Europe/Paris")
    ev = Event(
        uid="e1",
        start=datetime(2026, 5, 4, 9, 0, tzinfo=tz),
        end=datetime(2026, 5, 4, 10, 0, tzinfo=tz),
        title="Sync",
        location="",
        attendees=["a@x.com"],
        organizer="me@x.com",
        category="work",
        source_name="Work",
        description="",
    )
    out = client.per_meeting_prep([ev])
    assert "e1" in out
    assert out["e1"]["prep_notes"] == "Bring slides"
    assert len(out["e1"]["questions_to_prepare"]) == 2


@respx.mock
def test_narrative_tolerates_http_error(monkeypatch):
    client = _client(monkeypatch)
    respx.post("https://api.mistral.ai/v1/chat/completions").mock(return_value=Response(500))
    assert client.week_narrative({}) == ""


def test_disabled_when_no_key(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    c = MistralClient(LLMConfig())
    assert c.enabled is False
    assert c.week_narrative({}) == ""
    assert c.per_meeting_prep([]) == {}

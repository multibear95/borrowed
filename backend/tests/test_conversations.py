import asyncio
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from borrowed_backend.agents.state import DateReference, Extraction, Slots
from borrowed_backend.data.store import InMemoryStore
from borrowed_backend.main import create_app


class ScriptedLLM:
    def __init__(self, *extractions, fail_text=False):
        self.extractions = list(extractions)
        self.contexts = []
        self.fail_text = fail_text

    async def extract(self, context):
        self.contexts.append(context)
        result = self.extractions.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def text_stream(self, context):
        if self.fail_text:
            raise TimeoutError()
        yield "请补充城市和 EU 尺码。" if context["kind"] == "question" else "请查看实际推荐日期，确认后才预约。"

    async def close(self):
        pass


def complete(**changes):
    return Extraction(wear_date=DateReference(weekday=4), city="Hamburg", sizes_eu=[38], **changes)


def create(client):
    response = client.post("/api/conversations", json={"role": "borrower"})
    assert response.status_code == 201
    return response.json()["conversation_id"]


def turn(client, conversation_id, **payload):
    response = client.post(f"/api/conversations/{conversation_id}/turn", json=payload)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_events(response.text)
    assert events[-1] == {"event": "done", "conversation_id": conversation_id}
    return events


def parse_events(text):
    events = []
    for frame in text.split("\n\n"):
        if frame.startswith("event:"):
            name, data = frame.split("\n", 1)
            events.append({"event": name.removeprefix("event: "), **json.loads(data.removeprefix("data: "))})
    return events


def event(events, name):
    return next(item for item in events if item["event"] == name)


def confirmation(results):
    return dict(intent="book", garment_id=results["hits"][0]["garment"]["id"],
                confirmed=True, result_id=results["result_id"])


def test_full_flow_restart_and_idempotency(settings):
    seed_mtime = settings.catalog_path.stat().st_mtime_ns
    llm = ScriptedLLM(Extraction(wear_date=DateReference(weekday=4), occasion="gala"),
                      Extraction(city="Hamburg", sizes_eu=[38]))
    app = create_app(settings, borrower_llm=llm)
    with TestClient(app) as client:
        cid = create(client)
        first = turn(client, cid, text="我周五要参加晚宴")
        assert event(first, "question")["fields"] == ["city", "sizes_eu"]
        assert not app.state.store.reservations
        results = event(turn(client, cid, text="汉堡，EU 38"), "results")
        assert len(results["hits"]) <= 3
        assert app.state.store.conversations[cid].slots.result_request.limit == 3
        assert all(hit["feasibility"]["feasible"] for hit in results["hits"])
        assert results["hits"][0]["feasibility"]["wear_from"] == "2026-09-18"
        assert not app.state.store.reservations
        payload = confirmation(results)
        assert event(turn(client, cid, **{**payload, "confirmed": False}), "error")["code"] == "CONFIRMATION_REQUIRED"
        assert not app.state.store.reservations
        booking = event(turn(client, cid, **payload), "booking_claim")["booking"]
        assert booking["payment_taken"] is False
        assert len(app.state.store.reservations) == 1
        assert event(turn(client, cid, **payload), "booking_claim")["booking"]["already_existed"]
        hits = client.post("/api/garments/search", json={"city": "Hamburg", "sizes_eu": [38],
                           "wear_date": "2026-09-18"}).json()
        assert payload["garment_id"] not in [hit["garment"]["id"] for hit in hits]
    with TestClient(create_app(settings, borrower_llm=ScriptedLLM())) as client:
        recovered = event(turn(client, cid, **payload), "booking_claim")["booking"]
        assert recovered["booking_id"] == booking["booking_id"]
        assert recovered["already_existed"]
    assert settings.catalog_path.stat().st_mtime_ns == seed_mtime


def test_follow_up_date_keeps_already_supplied_city_and_size(settings):
    llm = ScriptedLLM(
        Extraction(city="Hamburg", sizes_eu=[38], occasion="party"),
        Extraction(wear_date=DateReference(weekday=4), clear_fields=["city", "sizes_eu"]),
    )
    app = create_app(settings, borrower_llm=llm)
    with TestClient(app) as client:
        cid = create(client)
        first = turn(client, cid, text="I have a birthday party in Hamburg. My EU size is 38.")
        assert event(first, "question")["fields"] == ["wear_date"]
        second = turn(client, cid, text="This Friday")
        assert event(second, "results")["hits"]
        slots = app.state.store.conversations[cid].slots.slots
        assert slots.city == "Hamburg"
        assert slots.sizes_eu == [38]


@pytest.mark.parametrize("change", [
    {"garment_id": "item-not-recommended"}, {"result_id": "stale"},
    {"confirmed": False}, {"garment_id": None}, {"result_id": None},
])
def test_confirmation_gate(settings, change):
    app = create_app(settings, borrower_llm=ScriptedLLM(complete()))
    with TestClient(app) as client:
        cid = create(client)
        results = event(turn(client, cid, text="Friday Hamburg EU 38"), "results")
        assert event(turn(client, cid, **{**confirmation(results), **change}), "error")
        assert not app.state.store.reservations


def test_no_prior_results_or_plain_booking_text(settings):
    app = create_app(settings, borrower_llm=ScriptedLLM(complete(), Extraction()))
    with TestClient(app) as client:
        cid = create(client)
        assert event(turn(client, cid, intent="book", confirmed=True,
                          garment_id="item-0000", result_id="forged"), "error")
        results = event(turn(client, cid, text="Hamburg EU 38 Friday"), "results")
        turn(client, cid, text=f"Please book {results['hits'][0]['garment']['id']} now")
        assert not app.state.store.reservations


def test_changed_conditions_invalidate_old_results(settings):
    app = create_app(settings, borrower_llm=ScriptedLLM(complete(), Extraction(city="Berlin")))
    with TestClient(app) as client:
        cid = create(client)
        old = event(turn(client, cid, text="Friday Hamburg EU 38"), "results")
        turn(client, cid, text="Actually Berlin")
        assert event(turn(client, cid, **confirmation(old)), "error")["code"] == "CONFIRMATION_REQUIRED"
        assert not app.state.store.reservations


def test_no_results_and_model_failure_are_recoverable(settings):
    app = create_app(settings, borrower_llm=ScriptedLLM(TimeoutError(), complete(max_price=0)))
    with TestClient(app) as client:
        cid = create(client)
        assert event(turn(client, cid, text="hello"), "error")["recoverable"]
        events = turn(client, cid, text="Hamburg EU 38 Friday, free only")
        assert event(events, "results")["hits"] == []
        assert "Try another date" in event(events, "token")["text"]
        assert not app.state.store.reservations


def test_composition_failure_keeps_results_and_question_fallback(settings):
    app = create_app(settings, borrower_llm=ScriptedLLM(Extraction(), complete(), fail_text=True))
    with TestClient(app) as client:
        cid = create(client)
        question = turn(client, cid, text="hello")
        assert len(event(question, "question")["fields"]) == 3
        results = turn(client, cid, text="Hamburg EU 38 Friday")
        assert event(results, "error")
        assert event(turn(client, cid, **confirmation(event(results, "results"))), "booking_claim")


def test_two_conversations_booking_conflict(settings):
    app = create_app(settings, borrower_llm=ScriptedLLM(complete(), complete()))
    with TestClient(app) as client:
        first, second = create(client), create(client)
        a = event(turn(client, first, text="Hamburg EU 38 Friday"), "results")
        b = event(turn(client, second, text="Hamburg EU 38 Friday"), "results")
        event(turn(client, first, **confirmation(a)), "booking_claim")
        conflict = turn(client, second, **confirmation(b))
        assert event(conflict, "availability")["feasibility"]["feasible"] is False
        assert event(conflict, "error")["code"] == "BOOKING_CONFLICT"
        assert len(app.state.store.reservations) == 1


def test_debug_and_multipart_validation(settings):
    app = create_app(settings.model_copy(update={"debug": True}), borrower_llm=ScriptedLLM(complete()))
    with TestClient(app) as client:
        cid = create(client)
        response = client.post(f"/api/conversations/{cid}/turn", files={"text": (None, "Hamburg Friday EU 38")})
        assert event(parse_events(response.text), "results")
        assert client.get(f"/api/debug/conversations/{cid}").json()["slots"]["slots"]["city"] == "Hamburg"
        assert client.post(f"/api/conversations/{cid}/turn", json={"text": ""}).status_code == 422
        assert client.post(f"/api/conversations/{cid}/turn", json={"intent": "book", "text": "change date"}).status_code == 422
        assert client.post("/api/conversations/missing/turn", json={"text": "hello"}).status_code == 404
        assert client.post(f"/api/conversations/{cid}/turn", files={"image": ("test.jpg", b"test")}).status_code == 400
    with TestClient(create_app(settings, borrower_llm=ScriptedLLM())) as client:
        assert client.get(f"/api/debug/conversations/{cid}").status_code == 404


def test_conversation_snapshot_failure(settings, monkeypatch):
    app = create_app(settings, borrower_llm=ScriptedLLM(complete()))
    with TestClient(app) as client:
        cid = create(client)
        original = app.state.store.conversations[cid]
        def fail(*args):
            raise OSError("disk full")
        monkeypatch.setattr("borrowed_backend.data.store.write_atomic", fail)
        assert event(turn(client, cid, text="Friday Hamburg EU 38"), "error")["code"] == "PERSISTENCE_FAILED"
        assert app.state.store.conversations[cid] == original
        assert not app.state.store.reservations


def test_invalid_dates_can_be_corrected(settings):
    app = create_app(settings, borrower_llm=ScriptedLLM(
        complete(return_date=DateReference(exact=date(2026, 9, 17))),
        Extraction(return_date=DateReference(exact=date(2026, 9, 21)))))
    with TestClient(app) as client:
        cid = create(client)
        assert event(turn(client, cid, text="invalid end date"), "error")["code"] == "INVALID_SLOTS"
        assert event(turn(client, cid, text="last wear day is September 21 2026"), "results")["hits"]


def test_relative_dates_and_clear_preferences():
    today = date(2026, 9, 16)
    assert DateReference(weekday=4).resolve(today) == date(2026, 9, 18)
    assert DateReference(weekday=4, week_offset=1).resolve(today) == date(2026, 9, 25)
    assert DateReference(days_from_today=1).resolve(today) == date(2026, 9, 17)
    assert DateReference(weekday=2).resolve(today) == today
    slots = Slots(wear_date=today, return_date=date(2026, 9, 20), max_price=20)
    merged = Extraction(wear_date=DateReference(weekday=4), clear_fields=["max_price"]).merge(slots, today)
    assert merged.return_date is None and merged.max_price is None


def test_failed_change_invalidates_previous_confirmation(settings):
    app = create_app(settings, borrower_llm=ScriptedLLM(complete(), TimeoutError()))
    with TestClient(app) as client:
        cid = create(client)
        old = event(turn(client, cid, text="Friday Hamburg EU 38"), "results")
        assert event(turn(client, cid, text="Actually next week"), "error")
        assert event(turn(client, cid, **confirmation(old)), "error")["code"] == "CONFIRMATION_REQUIRED"
        assert not app.state.store.reservations


def test_timeout_and_heartbeat(settings, monkeypatch):
    class SlowLLM(ScriptedLLM):
        async def extract(self, context):
            await asyncio.sleep(10)
            return complete()
    monkeypatch.setattr("borrowed_backend.api.conversations.HEARTBEAT_SECONDS", 0.01)
    app = create_app(settings.model_copy(update={"llm_timeout_s": 0.08}), borrower_llm=SlowLLM())
    with TestClient(app) as client:
        cid = create(client)
        response = client.post(f"/api/conversations/{cid}/turn", json={"text": "hello"})
        assert ": ping\n\n" in response.text
        assert event(parse_events(response.text), "error")["code"] == "LLM_TIMEOUT"
        assert not app.state.store.reservations


def test_missing_configuration(settings):
    with TestClient(create_app(settings)) as client:
        cid = create(client)
        assert event(turn(client, cid, text="hello"), "error")["code"] == "LLM_NOT_CONFIGURED"


def test_booking_snapshot_failure_and_retry(settings, monkeypatch):
    from borrowed_backend.data.store import write_atomic
    app = create_app(settings, borrower_llm=ScriptedLLM(complete()))
    with TestClient(app) as client:
        cid = create(client)
        payload = confirmation(event(turn(client, cid, text="Friday Hamburg EU 38"), "results"))
        def fail_bookings(path, data):
            if path.name == "bookings.json":
                raise OSError("disk full")
            write_atomic(path, data)
        monkeypatch.setattr("borrowed_backend.data.store.write_atomic", fail_bookings)
        failure = turn(client, cid, **payload)
        assert event(failure, "error")["code"] == "PERSISTENCE_FAILED"
        assert not any(item["event"] == "booking_claim" for item in failure)
        assert not app.state.store.reservations
        monkeypatch.setattr("borrowed_backend.data.store.write_atomic", write_atomic)
        assert event(turn(client, cid, **payload), "booking_claim")


def test_chat_snapshot_failure_after_booking_is_not_lost(settings, monkeypatch):
    from borrowed_backend.data.store import write_atomic
    app = create_app(settings, borrower_llm=ScriptedLLM(complete()))
    with TestClient(app) as client:
        cid = create(client)
        payload = confirmation(event(turn(client, cid, text="Friday Hamburg EU 38"), "results"))
        def fail_chat(path, data):
            if path.name == "conversations.json":
                raise OSError("disk full")
            write_atomic(path, data)
        monkeypatch.setattr("borrowed_backend.data.store.write_atomic", fail_chat)
        result = turn(client, cid, **payload)
        booked = event(result, "booking_claim")["booking"]
        assert event(result, "error")["code"] == "PERSISTENCE_FAILED"
        monkeypatch.setattr("borrowed_backend.data.store.write_atomic", write_atomic)
    with TestClient(create_app(settings, borrower_llm=ScriptedLLM())) as client:
        retry = event(turn(client, cid, **payload), "booking_claim")["booking"]
        assert retry["booking_id"] == booked["booking_id"] and retry["already_existed"]


def test_concurrent_confirmations_are_idempotent(settings):
    from concurrent.futures import ThreadPoolExecutor
    app = create_app(settings, borrower_llm=ScriptedLLM(complete()))
    with TestClient(app) as client:
        cid = create(client)
        payload = confirmation(event(turn(client, cid, text="Friday Hamburg EU 38"), "results"))
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: turn(client, cid, **payload), range(4)))
        bookings = [event(result, "booking_claim")["booking"] for result in results]
        assert len({booking["booking_id"] for booking in bookings}) == 1
        assert sum(not booking["already_existed"] for booking in bookings) == 1

"""Exercise the official MCP client over a real TCP/HTTP server, not ASGI mocks."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
import socket
import threading
import time
from uuid import UUID

import httpx
import jsonschema
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
import pytest
from pydantic import TypeAdapter
import uvicorn

from borrowed_backend.data.store import InMemoryStore
from borrowed_backend.main import create_app
from borrowed_backend.tools.registry import REGISTRY, invoke

SEARCH = {"city": "Hamburg", "sizes_eu": [38], "wear_date": "2026-09-18", "limit": 1000}


@pytest.fixture
def live_mcp(settings):
    app = create_app(settings)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "MCP HTTP server failed to start"
        yield f"http://127.0.0.1:{port}", app
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive(), "MCP lifespan failed to shut down"


@asynccontextmanager
async def connect(base):
    async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
        async with streamable_http_client(f"{base}/mcp", http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "MORE"
                yield session


def success(result):
    assert not result.isError, result.content
    assert json.loads(result.content[0].text) == result.structuredContent
    return result.structuredContent["result"]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def test_all_tools_match_registry_over_http(live_mcp, settings, monkeypatch):
    base, _ = live_mcp
    direct_store = InMemoryStore(settings.model_copy(update={"state_dir": settings.state_dir / "direct"}))
    # Fix generated booking IDs on both independent stores for exact payload comparison.
    monkeypatch.setattr("borrowed_backend.data.store.uuid4", lambda: UUID(int=12345))

    async def run():
        async with connect(base) as session:
            definitions = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert set(definitions) == {name for name, tool in REGISTRY.items() if tool.external}
            for name, tool in definitions.items():
                assert tool.inputSchema == REGISTRY[name].input.model_json_schema()
                assert tool.description == REGISTRY[name].description
                assert tool.annotations.readOnlyHint == (name != "create_booking")
                assert tool.annotations.idempotentHint
                assert tool.annotations.destructiveHint == (name == "create_booking")

            async def compare(name, payload):
                direct = await invoke(name, direct_store, payload)
                expected = TypeAdapter(REGISTRY[name].output).dump_python(direct, mode="json")
                response = await session.call_tool(name, payload)
                actual = success(response)
                jsonschema.validate(response.structuredContent, definitions[name].outputSchema)
                assert canonical(actual) == canonical(expected)
                return actual

            hits = await compare("search_garments", SEARCH)
            garment_id = hits[0]["garment"]["id"]
            await compare("get_garment", {"garment_id": garment_id})
            window = {key: SEARCH[key] for key in ("city", "sizes_eu", "wear_date")}
            await compare("check_availability", {**window, "garment_id": garment_id})
            booking = {**window, "garment_id": garment_id, "idempotency_key": "mcp-contract"}
            first = await compare("create_booking", booking)
            assert first["status"] == "reserved" and first["payment_taken"] is False
            retry = await compare("create_booking", booking)
            assert retry["booking_id"] == first["booking_id"] and retry["already_existed"]
            async with httpx.AsyncClient(base_url=base, trust_env=False) as rest:
                hits = (await rest.post("/api/garments/search", json=SEARCH)).json()
                assert garment_id not in {hit["garment"]["id"] for hit in hits}
                assert (await rest.post("/api/bookings", json=booking)).json() == retry
            restored = InMemoryStore(settings)
            assert (await restored.create_booking(REGISTRY["create_booking"].input(**booking))).already_existed
    asyncio.run(run())


def test_errors_and_hidden_tools(live_mcp, monkeypatch):
    base, _ = live_mcp

    async def run():
        async with connect(base) as session:
            for name, payload, reason in (
                ("missing_tool", {}, "UNKNOWN_TOOL"),
                ("get_garment", {"garment_id": "missing"}, "GARMENT_NOT_FOUND"),
                ("search_garments", {**SEARCH, "include_infeasible": True}, "INVALID_ARGUMENTS"),
                ("search_garments", {**SEARCH, "wear_date": "invalid"}, "INVALID_ARGUMENTS"),
                ("search_garments", {**SEARCH, "wear_date": "9999-12-31"}, "DATE_RANGE_OUT_OF_BOUNDS"),
                ("create_booking", {}, "INVALID_ARGUMENTS"),
            ):
                result = await session.call_tool(name, payload)
                assert result.isError and result.structuredContent["reason"] == reason
            # Empty results and infeasibility are valid business responses.
            assert success(await session.call_tool("search_garments", {**SEARCH, "city": "missing"})) == []
            hit = success(await session.call_tool("search_garments", SEARCH))[0]
            window = {key: SEARCH[key] for key in ("city", "sizes_eu", "wear_date")}
            args = {**window, "garment_id": hit["garment"]["id"]}
            unavailable = success(await session.call_tool("check_availability", {**args, "city": "Kiel"}))
            assert not unavailable["feasible"] and unavailable["reason"] == "WRONG_CITY"
            booked = success(await session.call_tool("create_booking", {**args, "idempotency_key": "first"}))
            reused = await session.call_tool("create_booking", {**args, "idempotency_key": "first", "city": "Kiel"})
            assert reused.isError and reused.structuredContent["reason"] == "IDEMPOTENCY_KEY_REUSED"
            conflict = await session.call_tool("create_booking", {**args, "idempotency_key": "second"})
            assert conflict.isError and conflict.structuredContent["reason"] == "OVERLAPS_BOOKING"
            assert conflict.structuredContent["feasibility"]["blocking_booking_id"] == booked["booking_id"]
            with monkeypatch.context() as patch:
                patch.setitem(REGISTRY, "get_garment", replace(REGISTRY["get_garment"], external=False))
                assert "get_garment" not in {tool.name for tool in (await session.list_tools()).tools}
                hidden = await session.call_tool("get_garment", {"garment_id": hit["garment"]["id"]})
                assert hidden.isError and hidden.structuredContent["reason"] == "UNKNOWN_TOOL"
    asyncio.run(run())


def test_mcp_and_rest_concurrency(live_mcp):
    base, _ = live_mcp

    async def run():
        async with connect(base) as session, httpx.AsyncClient(base_url=base, trust_env=False) as rest:
            garment_id = success(await session.call_tool("search_garments", SEARCH))[0]["garment"]["id"]
            args = {key: SEARCH[key] for key in ("city", "sizes_eu", "wear_date")}
            args["garment_id"] = garment_id

            async def reserve(index):
                payload = {**args, "idempotency_key": f"concurrent-{index}"}
                if index % 2:
                    result = await session.call_tool("create_booking", payload)
                    if result.isError:
                        assert result.structuredContent["reason"] == "OVERLAPS_BOOKING"
                    return not result.isError
                result = await rest.post("/api/bookings", json=payload)
                assert result.status_code in (200, 409)
                return result.status_code == 200

            assert sum(await asyncio.gather(*(reserve(n) for n in range(20)))) == 1
    asyncio.run(run())


def test_snapshot_failure_and_retry(live_mcp, monkeypatch):
    base, _ = live_mcp

    def fail(*args):
        raise OSError("Simulated disk failure")

    async def run():
        async with connect(base) as session:
            hits = success(await session.call_tool("search_garments", SEARCH))
            args = {key: SEARCH[key] for key in ("city", "sizes_eu", "wear_date")}
            args.update(garment_id=hits[0]["garment"]["id"], idempotency_key="retry-failure")
            with monkeypatch.context() as patch:
                patch.setattr("borrowed_backend.data.store.write_atomic", fail)
                result = await session.call_tool("create_booking", args)
                assert result.isError and result.structuredContent["reason"] == "PERSISTENCE_FAILED"
            assert success(await session.call_tool("search_garments", SEARCH)) == hits
            assert success(await session.call_tool("create_booking", args))["status"] == "reserved"
    asyncio.run(run())


def test_transport_path_and_headers(live_mcp):
    base, _ = live_mcp
    request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    }}
    with httpx.Client(base_url=base, trust_env=False, follow_redirects=False) as client:
        headers = {"Accept": "application/json, text/event-stream"}
        response = client.post("/mcp", json=request, headers=headers)
        assert response.status_code == 200
        assert response.json()["result"]["serverInfo"]["name"] == "MORE"
        assert "mcp-session-id" not in response.headers  # Stateless transport only; store is shared.
        assert client.post("/mcp", json=request, headers={**headers, "Host": "evil.example"}).status_code == 421
        assert client.post("/mcp", json=request, headers={**headers, "Origin": "https://evil.example"}).status_code == 403

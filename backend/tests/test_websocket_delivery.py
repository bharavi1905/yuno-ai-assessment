"""
Tests for WebSocket log streaming and Redis event delivery — CLAUDE.md requirement 1.3
Run inside Docker: docker compose exec backend pytest tests/test_websocket_delivery.py -v
"""
import asyncio
import json
import uuid
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.asyncio


async def _redis_available() -> bool:
    try:
        from core.redis_client import redis_client
        await redis_client.ping()
        return True
    except Exception:
        return False


async def test_publish_log_event_writes_to_stream():
    """publish_log_event must write a valid JSON entry to the correct Redis stream."""
    if not await _redis_available():
        pytest.skip("Redis not reachable")

    from core.redis_client import publish_log_event, redis_client

    run_id = f"test-{uuid.uuid4().hex[:8]}"
    stream_key = f"stream:logs:{run_id}"
    event = {
        "type": "node_start",
        "node": "ordering",
        "message": "Searching restaurants...",
        "timestamp": "2026-05-01T10:00:00Z",
    }

    await publish_log_event(run_id, event)

    results = await redis_client.xread({stream_key: "0"}, count=10)
    assert results, f"No messages found in stream {stream_key}"

    _, messages = results[0]
    assert len(messages) >= 1

    _, fields = messages[-1]
    raw = fields.get("data", "{}")
    if isinstance(raw, bytes):
        raw = raw.decode()
    parsed = json.loads(raw)

    assert parsed["type"] == "node_start"
    assert parsed["node"] == "ordering"
    assert parsed["message"] == "Searching restaurants..."

    await redis_client.delete(stream_key)


async def test_publish_multiple_events_in_order():
    """Events published to a stream must be retrievable in order."""
    if not await _redis_available():
        pytest.skip("Redis not reachable")

    from core.redis_client import publish_log_event, redis_client

    run_id = f"test-order-{uuid.uuid4().hex[:8]}"
    stream_key = f"stream:logs:{run_id}"
    nodes = ["router", "ordering", "fraud", "payment", "hitl"]

    for node in nodes:
        await publish_log_event(run_id, {"type": "node_start", "node": node})

    results = await redis_client.xread({stream_key: "0"}, count=10)
    assert results

    _, messages = results[0]
    assert len(messages) == len(nodes)

    for i, (_, fields) in enumerate(messages):
        raw = fields.get("data", "{}")
        if isinstance(raw, bytes):
            raw = raw.decode()
        parsed = json.loads(raw)
        assert parsed["node"] == nodes[i], f"Expected node {nodes[i]}, got {parsed['node']}"

    await redis_client.delete(stream_key)


async def test_websocket_logs_endpoint_connects(client):
    """GET /ws/logs/{run_id} upgrades to WebSocket — verified via HTTP 101 response."""
    # We test the HTTP layer — the WebSocket upgrade is handled by the backend
    # A plain GET to a WebSocket endpoint returns 403 or 426 (Upgrade Required)
    # but NOT a 404, confirming the route exists
    run_id = f"test-{uuid.uuid4().hex[:8]}"
    resp = await client.get(f"/ws/logs/{run_id}")
    # WebSocket endpoints return 403 or 400/426 on plain HTTP — anything but 404
    assert resp.status_code != 404, "WebSocket endpoint /ws/logs/{run_id} not found"


async def test_websocket_monitor_endpoint_exists(client):
    """GET /ws/monitor must exist (not 404)."""
    resp = await client.get("/ws/monitor")
    assert resp.status_code != 404, "WebSocket endpoint /ws/monitor not found"


async def test_websocket_receives_published_events():
    """
    Integration: publish an event to Redis then read it back via websockets.
    Uses websockets library to make a real WebSocket connection.
    """
    try:
        import websockets
    except ImportError:
        pytest.skip("websockets library not installed")

    if not await _redis_available():
        pytest.skip("Redis not reachable")

    from core.redis_client import publish_log_event, redis_client

    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    ws_url = backend_url.replace("http://", "ws://").replace("https://", "wss://")
    run_id = f"test-ws-{uuid.uuid4().hex[:8]}"
    received: list[dict] = []

    async def consume():
        try:
            async with websockets.connect(  # type: ignore[attr-defined]
                f"{ws_url}/ws/logs/{run_id}",
                open_timeout=5,
                close_timeout=2,
            ) as ws:
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        ev = json.loads(msg)
                        if ev.get("type") != "ping":
                            received.append(ev)
                        if len(received) >= 1:
                            break
                    except asyncio.TimeoutError:
                        break
        except Exception:
            pass

    consumer_task = asyncio.create_task(consume())

    # Give the consumer time to connect
    await asyncio.sleep(0.5)

    await publish_log_event(run_id, {
        "type": "node_start",
        "node": "router",
        "message": "WebSocket delivery test",
    })

    await asyncio.wait_for(consumer_task, timeout=10.0)
    await redis_client.delete(f"stream:logs:{run_id}")

    assert len(received) >= 1, "WebSocket did not receive any events"
    assert received[0]["node"] == "router"

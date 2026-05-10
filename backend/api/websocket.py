import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect

from core.redis_client import redis_client

# redis_client has decode_responses=True — all keys/values are str, not bytes


async def websocket_log_stream(websocket: WebSocket, run_id: str) -> None:
    """
    Streams log events for a specific run_id from Redis Stream to WebSocket.
    Reads from stream:logs:{run_id} using XREAD with blocking.
    """
    await websocket.accept()

    stream_key = f"stream:logs:{run_id}"
    last_id = "0"
    idle_ticks = 0
    max_idle_ticks = 300  # 300 × 1s = 5 minutes

    try:
        while True:
            results = await redis_client.xread(
                {stream_key: last_id},
                count=10,
                block=1000,
            )

            if results:
                idle_ticks = 0
                for _key, messages in results:
                    for msg_id, fields in messages:
                        last_id = msg_id
                        raw = fields.get("data", "{}")
                        if isinstance(raw, bytes):
                            raw = raw.decode()
                        event = json.loads(raw)
                        await websocket.send_json(event)

                        if event.get("type") in ("workflow_complete", "workflow_error"):
                            await websocket.close()
                            return
            else:
                idle_ticks += 1
                if idle_ticks % 30 == 0:
                    await websocket.send_json({"type": "ping"})
                if idle_ticks >= max_idle_ticks:
                    await websocket.close()
                    return

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close()
        except Exception:
            pass


async def ws_monitor_handler(websocket: WebSocket) -> None:
    """
    Streams latest events across ALL active runs for the live dashboard.
    Polls Redis SCAN for stream:logs:* keys, then XREAD from each.
    """
    await websocket.accept()

    last_ids: dict[str, str] = {}

    try:
        while True:
            # Scan for active log streams
            cursor: int = 0
            all_keys: list[str] = []
            cursor, found = await redis_client.scan(cursor, match="stream:logs:*", count=20)
            all_keys.extend(
                k.decode() if isinstance(k, bytes) else k for k in found
            )

            if all_keys:
                streams = {k: last_ids.get(k, "0") for k in all_keys}
                results = await redis_client.xread(streams, count=5, block=500)
                if results:
                    for stream_key, messages in results:
                        sk = stream_key.decode() if isinstance(stream_key, bytes) else stream_key
                        for msg_id, fields in messages:
                            last_ids[sk] = msg_id
                            raw = fields.get("data", "{}")
                            if isinstance(raw, bytes):
                                raw = raw.decode()
                            await websocket.send_json(json.loads(raw))
                else:
                    await asyncio.sleep(0.5)
                    await websocket.send_json({"type": "ping"})
            else:
                await asyncio.sleep(1)
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close()
        except Exception:
            pass

import json
from typing import AsyncGenerator

import redis.asyncio as aioredis

from core.config import settings


redis_client: aioredis.Redis = aioredis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    decode_responses=True,
)


async def init_redis() -> None:
    await redis_client.ping()


async def publish_log_event(run_id: str, event: dict) -> None:
    stream_key = f"stream:logs:{run_id}"
    await redis_client.xadd(stream_key, {"data": json.dumps(event)})


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    yield redis_client

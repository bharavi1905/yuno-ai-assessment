from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.database import init_db, init_checkpointer, close_checkpointer
from core.redis_client import init_redis
from api.routes.agents import router as agents_router
from api.routes.workflows import router as workflows_router
from api.routes.runs import router as runs_router
from api.routes.messages import router as messages_router
from api.websocket import websocket_log_stream, ws_monitor_handler

# Import all models so SQLModel metadata is populated before create_all
import models  # noqa: F401

# Import MCP tool modules to trigger @mcp.tool() registration BEFORE mounting
import mcp_tools.restaurant_search  # noqa: F401
import mcp_tools.menu_retrieval     # noqa: F401
import mcp_tools.payment_routing    # noqa: F401
import mcp_tools.fraud_scoring      # noqa: F401
import mcp_tools.notification       # noqa: F401
import mcp_tools.order_lookup       # noqa: F401

from mcp_tools.server import mcp as mcp_server


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    await init_redis()

    checkpointer = await init_checkpointer()

    from graph.builder import init_graphs
    await init_graphs(checkpointer)

    if settings.seed_data_on_startup:
        from scripts.seed import run_seeder
        await run_seeder()

    from tg_bot.bot import start_bot
    await start_bot()

    yield

    from tg_bot.bot import stop_bot
    await stop_bot()

    await close_checkpointer()


app = FastAPI(
    title="Agent Platform API",
    description="AI Agent Orchestration Platform",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount FastMCP SSE endpoint — agents connect via http://backend:8000/mcp
mcp_asgi = mcp_server.sse_app()
app.mount("/mcp", mcp_asgi)

# REST routers
app.include_router(agents_router, prefix="/api/agents", tags=["agents"])
app.include_router(workflows_router, prefix="/api/workflows", tags=["workflows"])
app.include_router(runs_router, prefix="/api/runs", tags=["runs"])
app.include_router(messages_router, prefix="/api/messages", tags=["messages"])


# WebSocket endpoints
@app.websocket("/ws/logs/{run_id}")
async def ws_logs(websocket: WebSocket, run_id: str) -> None:
    await websocket_log_stream(websocket, run_id)


@app.websocket("/ws/monitor")
async def ws_monitor(websocket: WebSocket) -> None:
    await ws_monitor_handler(websocket)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "environment": settings.environment}

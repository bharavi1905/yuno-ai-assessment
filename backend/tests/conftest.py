"""
Test configuration for the Agent Platform backend.
Tests run inside Docker where all services (Postgres, Redis) are available.
Use BACKEND_URL env var to override the target URL (default: http://localhost:8000).
"""
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


@pytest_asyncio.fixture
async def client():
    """AsyncClient pointed at the running FastAPI backend."""
    async with AsyncClient(base_url=BACKEND_URL, timeout=30.0) as ac:
        # Verify the backend is reachable — skip all tests if it is not
        try:
            resp = await ac.get("/health")
            resp.raise_for_status()
        except Exception as exc:
            pytest.skip(f"Backend not reachable at {BACKEND_URL}: {exc}")
        yield ac


def requires_openai(func):
    """Decorator: skip test if OPENAI_API_KEY is not a real key."""
    return pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY", "").startswith("your_"),
        reason="OPENAI_API_KEY not configured — skipping LLM integration test",
    )(func)

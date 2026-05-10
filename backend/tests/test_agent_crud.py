"""
Tests for Agent CRUD API — CLAUDE.md requirement 1.3
Covers: create, list, get, update, delete, duplicate name rejection, required fields.
Run inside Docker: docker compose exec backend pytest tests/test_agent_crud.py -v
"""
import uuid
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# Use a unique suffix per test run to avoid name collisions across runs
_RUN_ID = uuid.uuid4().hex[:6]


def agent_name(label: str) -> str:
    return f"Test-{label}-{_RUN_ID}"


async def test_create_agent_success(client: AsyncClient):
    payload = {
        "name": agent_name("Create"),
        "role": "ordering",
        "system_prompt": "You search for restaurants matching user constraints.",
        "model": "gpt-4o-mini",
        "tools": ["restaurant_search"],
        "channels": [],
    }
    resp = await client.post("/api/agents", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == payload["name"]
    assert data["role"] == "ordering"
    assert data["model"] == "gpt-4o-mini"
    assert "restaurant_search" in data["tools"]
    assert "id" in data
    assert "created_at" in data


async def test_create_agent_all_fields(client: AsyncClient):
    payload = {
        "name": agent_name("AllFields"),
        "role": "custom",
        "system_prompt": "Full-featured agent.",
        "model": "gpt-4o",
        "tools": ["restaurant_search", "menu_retrieval"],
        "channels": ["Telegram"],
        "schedule": "0 9 * * *",
        "memory_enabled": True,
        "memory_window": 20,
        "skills": ["search", "recommend"],
        "interaction_rules": "Be concise.",
    }
    resp = await client.post("/api/agents", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["memory_enabled"] is True
    assert data["memory_window"] == 20
    assert "search" in data["skills"]
    assert data["schedule"] == "0 9 * * *"
    assert data["interaction_rules"] == "Be concise."


async def test_create_agent_duplicate_name(client: AsyncClient):
    payload = {
        "name": agent_name("Duplicate"),
        "role": "fraud",
        "system_prompt": "Fraud detection agent.",
        "model": "gpt-4o-mini",
        "tools": [],
        "channels": [],
    }
    resp1 = await client.post("/api/agents", json=payload)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/agents", json=payload)
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"].lower()


async def test_create_agent_missing_required_fields(client: AsyncClient):
    # Missing name
    resp = await client.post("/api/agents", json={
        "role": "ordering",
        "system_prompt": "Test prompt.",
        "model": "gpt-4o-mini",
        "tools": [],
        "channels": [],
    })
    assert resp.status_code == 422

    # Missing role
    resp = await client.post("/api/agents", json={
        "name": agent_name("NoRole"),
        "system_prompt": "Test prompt.",
        "model": "gpt-4o-mini",
        "tools": [],
        "channels": [],
    })
    assert resp.status_code == 422

    # Missing system_prompt
    resp = await client.post("/api/agents", json={
        "name": agent_name("NoPrompt"),
        "role": "ordering",
        "model": "gpt-4o-mini",
        "tools": [],
        "channels": [],
    })
    assert resp.status_code == 422


async def test_list_agents(client: AsyncClient):
    resp = await client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


async def test_list_agents_with_role_filter(client: AsyncClient):
    # Create an agent with a distinct role
    name = agent_name("RoleFilter")
    await client.post("/api/agents", json={
        "name": name,
        "role": "notification",
        "system_prompt": "Sends notifications.",
        "model": "gpt-4o-mini",
        "tools": [],
        "channels": [],
    })

    resp = await client.get("/api/agents?role=notification")
    assert resp.status_code == 200
    agents = resp.json()
    assert all(a["role"] == "notification" for a in agents)


async def test_get_agent_by_id(client: AsyncClient):
    create_resp = await client.post("/api/agents", json={
        "name": agent_name("GetById"),
        "role": "payment",
        "system_prompt": "Payment routing agent.",
        "model": "gpt-4o-mini",
        "tools": ["payment_routing"],
        "channels": [],
    })
    assert create_resp.status_code == 201
    agent_id = create_resp.json()["id"]

    resp = await client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == agent_id
    assert data["role"] == "payment"


async def test_get_agent_not_found(client: AsyncClient):
    resp = await client.get("/api/agents/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_get_agent_invalid_uuid(client: AsyncClient):
    resp = await client.get("/api/agents/not-a-valid-uuid")
    assert resp.status_code == 404


async def test_update_agent(client: AsyncClient):
    create_resp = await client.post("/api/agents", json={
        "name": agent_name("Update"),
        "role": "complaint",
        "system_prompt": "Original prompt.",
        "model": "gpt-4o-mini",
        "tools": [],
        "channels": [],
    })
    assert create_resp.status_code == 201
    agent_id = create_resp.json()["id"]

    resp = await client.put(f"/api/agents/{agent_id}", json={
        "system_prompt": "Updated prompt.",
        "model": "gpt-4o",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["system_prompt"] == "Updated prompt."
    assert data["model"] == "gpt-4o"
    assert data["name"] == agent_name("Update")  # name unchanged
    assert data["role"] == "complaint"             # role unchanged


async def test_update_agent_not_found(client: AsyncClient):
    resp = await client.put(
        "/api/agents/00000000-0000-0000-0000-000000000000",
        json={"system_prompt": "Ghost update."},
    )
    assert resp.status_code == 404


async def test_delete_agent(client: AsyncClient):
    create_resp = await client.post("/api/agents", json={
        "name": agent_name("Delete"),
        "role": "custom",
        "system_prompt": "To be deleted.",
        "model": "gpt-4o-mini",
        "tools": [],
        "channels": [],
    })
    assert create_resp.status_code == 201
    agent_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/agents/{agent_id}")
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/agents/{agent_id}")
    assert get_resp.status_code == 404


async def test_delete_agent_not_found(client: AsyncClient):
    resp = await client.delete("/api/agents/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404

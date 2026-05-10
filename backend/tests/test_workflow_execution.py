"""
Integration tests for workflow execution — CLAUDE.md requirement 1.3
Tests that use LLM calls are skipped if OPENAI_API_KEY is not configured.
Run inside Docker: docker compose exec backend pytest tests/test_workflow_execution.py -v
"""
import uuid
import pytest
import sys
import os

# Ensure backend package root is on sys.path when running inside Docker (/app)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import requires_openai

pytestmark = pytest.mark.asyncio


async def test_graph_compiles():
    """Both graphs must compile at startup — no LLM call needed."""
    from graph.builder import GRAPHS
    assert "food_ordering" in GRAPHS, "food_ordering graph not found in GRAPHS"
    assert "complaint_resolution" in GRAPHS, "complaint_resolution graph not found in GRAPHS"
    assert GRAPHS["food_ordering"] is not None
    assert GRAPHS["complaint_resolution"] is not None


async def test_agent_state_schema():
    """AgentState TypedDict must contain all required fields."""
    from graph.state import AgentState

    required_fields = [
        "run_id", "workflow_type", "telegram_chat_id", "user_id",
        "messages", "user_message", "current_step", "workflow_status",
        "execution_logs", "error",
        "order_constraints", "order_summary",
        "fraud_result", "payment_result",
        "resolution_result", "complaint_reprompt",
        "hitl_status", "hitl_prompt", "hitl_response", "hitl_expires_at", "hitl_action",
        "token_usage",
    ]
    annotations = AgentState.__annotations__
    for field in required_fields:
        assert field in annotations, f"AgentState missing required field: '{field}'"


async def test_edges_compile():
    """All edge routing functions must be importable and callable."""
    from graph.edges import (
        route_from_router,
        route_after_fraud,
        route_after_hitl,
    )
    base_state = {
        "workflow_type": "food_ordering",
        "fraud_result": {"decision": "approve"},
        "hitl_status": "confirmed",
        "payment_result": {"success": True},
    }
    assert route_from_router(base_state) == "ordering"  # type: ignore[arg-type]

    base_state["workflow_type"] = "complaint_resolution"
    assert route_from_router(base_state) == "complaint"  # type: ignore[arg-type]

    base_state["fraud_result"] = {"decision": "block"}
    assert route_after_fraud(base_state) == "notification"  # type: ignore[arg-type]

    base_state["fraud_result"] = {"decision": "approve"}
    assert route_after_fraud(base_state) == "hitl"  # complaint_resolution goes to hitl

    base_state["workflow_type"] = "food_ordering"
    assert route_after_fraud(base_state) == "payment"  # type: ignore[arg-type]

    base_state["hitl_status"] = "rejected"
    from langgraph.graph import END
    assert route_after_hitl(base_state) == END  # type: ignore[arg-type]


async def test_nodes_importable():
    """All node functions must be importable without error."""
    from graph.nodes import (
        router_node,
        ordering_node,
        fraud_node,
        payment_node,
        hitl_node,
        notification_node,
        complaint_node,
    )
    assert callable(router_node)
    assert callable(ordering_node)
    assert callable(fraud_node)
    assert callable(payment_node)
    assert callable(hitl_node)
    assert callable(notification_node)
    assert callable(complaint_node)


@requires_openai
async def test_food_ordering_graph_runs_to_hitl():
    """
    Full integration: food_ordering graph runs until it pauses at interrupt().
    Verifies the graph executes: router → ordering → hitl.
    Requires a real OPENAI_API_KEY and running PostgreSQL (checkpointer).
    """
    from graph.builder import get_graph

    graph = get_graph("food_ordering")
    chat_id = f"test_{uuid.uuid4().hex[:8]}"

    initial_state = {
        "run_id": str(uuid.uuid4()),
        "workflow_type": "food_ordering",
        "telegram_chat_id": chat_id,
        "user_id": chat_id,
        "messages": [],
        "user_message": "Order chicken biryani under Rs300 in Hyderabad",
        "current_step": "",
        "workflow_status": "running",
        "execution_logs": [],
        "error": None,
        "order_constraints": {"max_price": 300, "min_rating": 4.0, "city": "Hyderabad", "cuisine": "biryani"},
        "order_summary": None,
        "ordering_messages": [],
        "ordering_agent_thread_id": "",
        "fraud_result": None,
        "payment_result": None,
        "resolution_result": None,
        "complaint_reprompt": "",
        "hitl_status": "not_required",
        "hitl_prompt": "",
        "hitl_response": "",
        "hitl_expires_at": "",
        "hitl_action": "place_order",
        "token_usage": {},
    }

    config = {"configurable": {"thread_id": chat_id}}
    result = await graph.ainvoke(initial_state, config=config)

    assert result.get("hitl_status") == "pending", (
        f"Expected hitl_status=pending, got: {result.get('hitl_status')}. "
        f"Error: {result.get('error')}"
    )
    assert result.get("hitl_prompt"), "HITL prompt must not be empty"
    assert result.get("order_summary") is not None, "Order summary must be populated"


@requires_openai
async def test_food_ordering_hitl_confirmed():
    """Resume after HITL with YES — workflow must complete."""
    from graph.builder import get_graph
    from langgraph.types import Command

    graph = get_graph("food_ordering")
    chat_id = f"test_{uuid.uuid4().hex[:8]}"

    initial_state = {
        "run_id": str(uuid.uuid4()),
        "workflow_type": "food_ordering",
        "telegram_chat_id": chat_id,
        "user_id": chat_id,
        "messages": [],
        "user_message": "Order chicken biryani under Rs300 in Hyderabad",
        "current_step": "",
        "workflow_status": "running",
        "execution_logs": [],
        "error": None,
        "order_constraints": {"max_price": 300, "city": "Hyderabad"},
        "order_summary": None,
        "ordering_messages": [],
        "ordering_agent_thread_id": "",
        "fraud_result": None,
        "payment_result": None,
        "resolution_result": None,
        "complaint_reprompt": "",
        "hitl_status": "not_required",
        "hitl_prompt": "",
        "hitl_response": "",
        "hitl_expires_at": "",
        "hitl_action": "place_order",
        "token_usage": {},
    }

    config = {"configurable": {"thread_id": chat_id}}

    # Phase 1: run to HITL interrupt
    await graph.ainvoke(initial_state, config=config)

    # Phase 2: resume with YES
    result = await graph.ainvoke(
        Command(resume={"approved": True, "raw_response": "YES"}),
        config=config,
    )

    assert result.get("workflow_status") == "completed", (
        f"Expected workflow_status=completed, got: {result.get('workflow_status')}"
    )
    assert result.get("hitl_status") == "confirmed"


@requires_openai
async def test_food_ordering_hitl_rejected():
    """Resume after HITL with NO — hitl_status must be rejected."""
    from graph.builder import get_graph
    from langgraph.types import Command

    graph = get_graph("food_ordering")
    chat_id = f"test_{uuid.uuid4().hex[:8]}"

    initial_state = {
        "run_id": str(uuid.uuid4()),
        "workflow_type": "food_ordering",
        "telegram_chat_id": chat_id,
        "user_id": chat_id,
        "messages": [],
        "user_message": "Order biryani in Hyderabad under Rs300",
        "current_step": "",
        "workflow_status": "running",
        "execution_logs": [],
        "error": None,
        "order_constraints": {"max_price": 300, "city": "Hyderabad"},
        "order_summary": None,
        "ordering_messages": [],
        "ordering_agent_thread_id": "",
        "fraud_result": None,
        "payment_result": None,
        "resolution_result": None,
        "complaint_reprompt": "",
        "hitl_status": "not_required",
        "hitl_prompt": "",
        "hitl_response": "",
        "hitl_expires_at": "",
        "hitl_action": "place_order",
        "token_usage": {},
    }

    config = {"configurable": {"thread_id": chat_id}}
    await graph.ainvoke(initial_state, config=config)

    result = await graph.ainvoke(
        Command(resume={"approved": False, "raw_response": "NO"}),
        config=config,
    )

    assert result.get("hitl_status") == "rejected"

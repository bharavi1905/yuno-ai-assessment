import logging

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph

from graph.edges import (
    route_after_fraud,
    route_after_hitl,
    route_from_router,
)
from graph.nodes import (
    complaint_node,
    fraud_node,
    hitl_node,
    notification_node,
    ordering_node,
    payment_node,
    router_node,
)
from graph.state import AgentState

logger = logging.getLogger(__name__)

GRAPHS: dict = {}


def build_food_ordering_graph(checkpointer: AsyncPostgresSaver):
    # Flow: router → ordering → hitl → fraud → payment → notification
    # HITL fires early so corrections loop back to ordering
    graph = StateGraph(AgentState)

    graph.add_node("router",        router_node)
    graph.add_node("ordering",      ordering_node)
    graph.add_node("hitl",          hitl_node)
    graph.add_node("fraud",         fraud_node)
    graph.add_node("payment",       payment_node)
    graph.add_node("notification",  notification_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", route_from_router)
    graph.add_edge("ordering",     "hitl")
    graph.add_conditional_edges(
        "hitl",
        route_after_hitl,
        {"fraud": "fraud", "ordering": "ordering", END: END},
    )
    graph.add_conditional_edges("fraud", route_after_fraud)
    graph.add_edge("payment",      "notification")
    graph.add_edge("notification", END)

    return graph.compile(checkpointer=checkpointer)


def build_complaint_resolution_graph(checkpointer: AsyncPostgresSaver):
    graph = StateGraph(AgentState)

    graph.add_node("router",        router_node)
    graph.add_node("complaint",     complaint_node)
    graph.add_node("fraud",         fraud_node)
    graph.add_node("hitl",          hitl_node)
    graph.add_node("ordering",      ordering_node)  # for confirmed re-order path
    graph.add_node("notification",  notification_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", route_from_router)
    graph.add_edge("complaint",    "fraud")
    graph.add_conditional_edges(
        "fraud",
        route_after_fraud,
        {"hitl": "hitl", "notification": "notification"},
    )
    graph.add_conditional_edges(
        "hitl",
        route_after_hitl,
        {"complaint": "complaint", "ordering": "ordering", "notification": "notification", END: END},
    )
    graph.add_edge("ordering",     "hitl")
    graph.add_edge("notification", END)

    return graph.compile(checkpointer=checkpointer)


async def init_graphs(checkpointer: AsyncPostgresSaver) -> None:
    from core.checkpointer import set_checkpointer
    set_checkpointer(checkpointer)
    GRAPHS["food_ordering"]        = build_food_ordering_graph(checkpointer)
    GRAPHS["complaint_resolution"] = build_complaint_resolution_graph(checkpointer)
    logger.info("LangGraph graphs compiled and cached: %s", list(GRAPHS.keys()))


def get_graph(workflow_type: str):
    graph = GRAPHS.get(workflow_type)
    if not graph:
        raise ValueError(f"No compiled graph for workflow_type: {workflow_type}")
    return graph

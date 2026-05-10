"""Langfuse observability integration for LangChain/LangGraph agents.

Usage in a node (async function):

    from core.observability import langfuse_node_span

    with langfuse_node_span(run_id=run_id, user_id="...", workflow_type="food_ordering", node_name="ordering") as lf_callbacks:
        agent_config = {"configurable": {"thread_id": thread_id}, "run_name": "ordering-agent"}
        if lf_callbacks:
            agent_config["callbacks"] = lf_callbacks
        await agent.ainvoke(input, config=agent_config)

The sync `with` block correctly propagates context to `await` calls inside it.
Langfuse is optional — if keys are absent the context manager yields [] and is a no-op.
"""

import logging
import uuid
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

_CallbackHandler = None
try:
    from langfuse.langchain import CallbackHandler
    _CallbackHandler = CallbackHandler
except ImportError:
    try:
        from langfuse.callback import CallbackHandler  # v2 fallback
        _CallbackHandler = CallbackHandler
    except ImportError:
        pass


def _is_enabled() -> bool:
    if _CallbackHandler is None:
        return False
    try:
        from core.config import settings
        return bool(settings.langfuse_secret_key and settings.langfuse_public_key)
    except Exception:
        return False


@contextmanager
def langfuse_node_span(
    *,
    run_id: str = "",
    user_id: str = "",
    workflow_type: str = "",
    node_name: str = "",
) -> Generator[list, None, None]:
    """Context manager that creates a Langfuse parent span for a node execution.

    Yields a callbacks list to pass into LangChain/LangGraph invoke configs.
    If Langfuse is disabled, yields [] and is a no-op.

    The deterministic trace_id (uuid5 of run_id+node_name) groups both the
    initial invoke and any resume/correction calls for the same node under
    one Langfuse trace. session_id=run_id links all nodes in a run together
    in the Sessions view.
    """
    if not _is_enabled():
        yield []
        return

    try:
        from langfuse import get_client
        lf = get_client()

        # Deterministic trace_id: same run_id + node_name always maps to the same trace.
        # This groups the initial agent call and any HITL correction resumes together.
        trace_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"{run_id}:{node_name}").hex

        with lf.start_as_current_span(
            trace_context={"trace_id": trace_id},
            name=f"{workflow_type}/{node_name}",
        ):
            lf.update_current_trace(
                session_id=run_id,
                user_id=user_id or "anonymous",
                tags=[t for t in [workflow_type, node_name, "agent-platform"] if t],
            )
            active_trace_id = lf.get_current_trace_id() or trace_id
            handler = _CallbackHandler(trace_context={"trace_id": active_trace_id})
            yield [handler]

    except Exception as exc:
        logger.warning("Langfuse span creation failed: %s", exc)
        yield []

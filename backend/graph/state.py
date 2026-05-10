from typing import Optional, TypedDict


class AgentState(TypedDict):
    # Identity
    run_id: str
    workflow_type: str           # food_ordering | complaint_resolution
    telegram_chat_id: str
    user_id: str

    # Conversation
    messages: list[dict]
    user_message: str

    # Execution tracking
    current_step: str            # active node name — drives React Flow highlighting
    workflow_status: str         # running|hitl_pending|completed|failed|cancelled
    execution_logs: list[dict]   # events pushed to Redis → WebSocket → UI
    error: Optional[str]

    # Ordering
    order_constraints: dict
    order_summary: Optional[dict]
    ordering_messages: list[dict]   # kept for backward compat; agent state now persisted by checkpointer
    ordering_agent_thread_id: str   # thread_id for the inner ordering agent (create_agent graph)

    # Fraud
    fraud_result: Optional[dict]

    # Payment
    payment_result: Optional[dict]

    # Complaint resolution
    resolution_result: Optional[dict]   # {resolution_type, reason, compensation_amount, original_item, restaurant_name, order_id}
    complaint_reprompt: str             # user's re-prompt text when changing resolution; "" if not re-prompted

    # HITL
    hitl_status: str             # not_required|pending|confirmed|rejected|expired
    hitl_prompt: str
    hitl_response: str
    hitl_expires_at: str         # ISO timestamp; session expires after 10 minutes
    hitl_action: str             # place_order | resolve_complaint

    # Token tracking
    token_usage: dict            # {agent_name: {input: n, output: n, cost_usd: f}}

from langgraph.graph import END

from graph.state import AgentState


def route_from_router(state: AgentState) -> str:
    if state["workflow_type"] == "food_ordering":
        return "ordering"
    if state["workflow_type"] == "complaint_resolution":
        return "complaint"
    return END


def route_after_fraud(state: AgentState) -> str:
    fraud = state.get("fraud_result")
    if fraud and fraud.get("decision") == "block":
        return "notification"
    if state.get("workflow_type") == "complaint_resolution":
        return "hitl"
    return "payment"


def route_after_hitl(state: AgentState) -> str:
    status = state.get("hitl_status")
    workflow_type = state.get("workflow_type")

    if workflow_type == "complaint_resolution":
        if status == "reprompt":
            return "complaint"
        if status == "confirmed":
            hitl_action = state.get("hitl_action", "")
            if hitl_action == "resolve_complaint":
                resolution = state.get("resolution_result") or {}
                if resolution.get("resolution_type") == "reorder":
                    return "ordering"   # search & confirm the new food order
                return "notification"  # compensate — close immediately
            # hitl_action == "place_order": food order confirmed after search
            return "notification"
        # rejected / expired → escalation notification
        return "notification"

    # food_ordering
    if status == "confirmed":
        if workflow_type == "food_ordering":
            return "fraud"
        return "notification"
    if status == "retry_order" and workflow_type == "food_ordering":
        return "ordering"
    return END



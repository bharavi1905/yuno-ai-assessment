import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from langgraph.types import interrupt
from sqlalchemy import select

from agents.base import get_mcp_tools
from core.database import AsyncSessionFactory
from core.redis_client import publish_log_event
from graph.state import AgentState
from models.agent import Agent

logger = logging.getLogger(__name__)

# Approximate cost per 1M tokens (for display transparency only — not billing)
COST_PER_1M_TOKENS: dict[str, dict[str, float]] = {
    "gpt-4o":      {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini": {"input": 0.15,  "output": 0.60},
}


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    key = model.replace("openai:", "")
    rates = COST_PER_1M_TOKENS.get(key, COST_PER_1M_TOKENS["gpt-4o-mini"])
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


async def _persist_message(run_id: str, node_name: str, event_type: str, payload: dict) -> None:
    """Write node event to run_messages table (fire-and-forget via create_task)."""
    try:
        from models.message import RunMessage
        async with AsyncSessionFactory() as session:
            session.add(RunMessage(
                run_id=run_id,
                node_name=node_name,
                event_type=event_type,
                payload=payload,
            ))
            await session.commit()
    except Exception as exc:
        logger.warning("Failed to persist message run_id=%s node=%s: %s", run_id, node_name, exc)


async def _log(run_id: str, node: str, event_type: str, data: dict) -> None:
    payload = {
        "type": event_type,
        "node": node,
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data,
    }
    await publish_log_event(run_id, payload)
    asyncio.create_task(_persist_message(run_id, node, event_type, payload))


def _extract_token_usage(response: Any, model: str) -> dict[str, Any]:
    usage: dict[str, Any] = {}
    try:
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            meta = response.usage_metadata
            inp = getattr(meta, "input_tokens", 0) or 0
            out = getattr(meta, "output_tokens", 0) or 0
            usage = {
                "input": inp,
                "output": out,
                "cost_usd": _calculate_cost(model, inp, out),
            }
        elif isinstance(response, dict) and "messages" in response:
            msgs = response["messages"]
            if msgs:
                last = msgs[-1]
                if hasattr(last, "usage_metadata") and last.usage_metadata:
                    meta = last.usage_metadata
                    inp = getattr(meta, "input_tokens", 0) or 0
                    out = getattr(meta, "output_tokens", 0) or 0
                    usage = {
                        "input": inp,
                        "output": out,
                        "cost_usd": _calculate_cost(model, inp, out),
                    }
    except Exception:
        pass
    return usage


async def _load_agent_config(role: str) -> dict:
    """Load agent config from DB; fall back to defaults if not found."""
    try:
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(Agent).where(Agent.role == role).limit(1)
            )
            agent = result.scalars().first()
            if agent:
                return {
                    "role": agent.role,
                    "model": agent.model,
                    "system_prompt": agent.system_prompt,
                    "tools": agent.tools,
                }
    except Exception as exc:
        logger.warning("Could not load agent config for role=%s: %s", role, exc)
    return {"role": role, "model": "openai:gpt-4o-mini"}


async def router_node(state: AgentState) -> dict:
    await _log(state["run_id"], "router", "node_start", {
        "message": "Workflow started",
        "user_message": state.get("user_message", ""),
        "workflow_type": state.get("workflow_type", ""),
    })

    workflow_type = state.get("workflow_type", "")
    if workflow_type not in ("food_ordering", "complaint_resolution"):
        error = f"Unknown workflow_type: {workflow_type}"
        await _log(state["run_id"], "router", "node_error", {"error": error})
        return {**state, "workflow_status": "failed", "error": error, "current_step": "router"}

    updated = {
        **state,
        "current_step": "router",
        "workflow_status": "running",
    }

    await _log(state["run_id"], "router", "node_complete", {
        "workflow_type": workflow_type,
    })
    return updated


async def ordering_node(state: AgentState) -> dict:
    """Invoke the ordering agent (create_agent + HumanInTheLoopMiddleware).

    On fresh start: invoke the agent with the user's message. The agent calls
    restaurant_search, menu_retrieval, then confirm_order. HumanInTheLoopMiddleware
    intercepts confirm_order and fires interrupt(), pausing the agent. ordering_node
    extracts the order_summary from the interrupt data and returns it in AgentState.

    On correction (hitl_status == "retry_order"): resume the inner agent with a
    reject decision containing the user's correction text. The agent re-searches
    with the feedback, calls confirm_order again (middleware fires again), and
    ordering_node extracts the new order_summary.

    The inner agent is persisted by the outer graph's checkpointer under thread_id
    "ordering:{run_id}", separate from the outer graph's own thread.
    """
    await _log(state["run_id"], "ordering", "node_start", {
        "message": "Searching restaurants...",
    })

    from core.checkpointer import get_checkpointer
    from core.observability import langfuse_node_span
    from agents.ordering import build_ordering_agent
    from langchain_core.messages import HumanMessage
    from langgraph.types import Command

    config = await _load_agent_config("ordering")
    checkpointer = get_checkpointer()
    agent = await build_ordering_agent(config, checkpointer=checkpointer)

    # The inner ordering agent uses a sub-thread so it doesn't collide with the outer graph
    run_id = state["run_id"]
    ordering_agent_thread_id = state.get("ordering_agent_thread_id") or f"ordering:{run_id}"

    is_correction = (
        state.get("hitl_status") == "retry_order"
        and state.get("ordering_agent_thread_id")
    )

    # Both the initial invoke and any correction resume run inside one Langfuse span.
    # The deterministic trace_id in langfuse_node_span groups them under the same trace.
    with langfuse_node_span(
        run_id=run_id,
        user_id=state.get("user_id", ""),
        workflow_type=state.get("workflow_type", ""),
        node_name="ordering",
    ) as lf_callbacks:
        agent_config: dict = {
            "configurable": {"thread_id": ordering_agent_thread_id},
            "run_name": "ordering-agent",
        }
        if lf_callbacks:
            agent_config["callbacks"] = lf_callbacks

        if is_correction:
            correction_raw = state.get("hitl_response") or "Please suggest different options."
            # Append the previously shown restaurant so the agent knows to skip it.
            prev_restaurant = (state.get("order_summary") or {}).get("restaurant_name", "")
            if prev_restaurant:
                correction = (
                    f"{correction_raw}\n\n"
                    f"[System context: you previously suggested {prev_restaurant}. "
                    f"Do NOT recommend {prev_restaurant} again — choose a different restaurant.]"
                )
            else:
                correction = correction_raw
            await _log(run_id, "ordering", "node_info", {
                "message": "Resuming ordering agent with user correction",
                "correction": correction,
            })
            try:
                await agent.ainvoke(
                    Command(resume={"decisions": [{"type": "reject", "message": correction}]}),
                    config=agent_config,
                )
            except Exception as exc:
                if type(exc).__name__ == "GraphInterrupt":
                    pass  # inner agent re-interrupted at confirm_order — state is checkpointed
                else:
                    logger.warning("Ordering agent correction resume error: %s", exc)
        else:
            initial_messages = [HumanMessage(content=state.get("user_message", ""))]
            try:
                await agent.ainvoke({"messages": initial_messages}, config=agent_config)
            except Exception as exc:
                if type(exc).__name__ == "GraphInterrupt":
                    pass  # inner agent interrupted at confirm_order — state is checkpointed
                else:
                    logger.warning("Ordering agent initial invoke error: %s", exc)

    # Inspect inner agent state to extract the confirm_order args from the interrupt
    order_summary: dict = {}
    try:
        agent_state = await agent.aget_state(agent_config)
        interrupted_tasks = [
            t for t in (agent_state.tasks or []) if getattr(t, "interrupts", None)
        ]
        logger.info(
            "ordering_node aget_state: tasks=%d interrupted=%d next=%s",
            len(agent_state.tasks or []),
            len(interrupted_tasks),
            agent_state.next,
        )
        if interrupted_tasks:
            interrupt_value = interrupted_tasks[0].interrupts[0].value
            logger.info("interrupt_value type=%s keys=%s", type(interrupt_value).__name__,
                        list(interrupt_value.keys()) if isinstance(interrupt_value, dict) else "N/A")
            if isinstance(interrupt_value, dict):
                action_requests = interrupt_value.get("action_requests", [])
                if action_requests:
                    order_summary = action_requests[0].get("args", {})
        elif agent_state.values:
            # Agent completed without interrupt — try to parse order from last AI message
            msgs = agent_state.values.get("messages", [])
            for msg in reversed(msgs):
                content = getattr(msg, "content", "")
                if content and isinstance(content, str):
                    try:
                        parsed = json.loads(content.strip())
                        if isinstance(parsed, dict):
                            order_summary = parsed
                            break
                    except (json.JSONDecodeError, Exception):
                        pass
    except Exception as exc:
        logger.warning("Could not inspect ordering agent state: %s", exc)

    # Guarantee order_summary is never empty so the HITL panel always shows something
    if not order_summary:
        logger.warning("ordering_node: no order_summary extracted — falling back to no-match")
        order_summary = {
            "no_match": True,
            "reason": "No matching restaurant found. Please try a different search.",
        }

    hitl_prompt = _format_food_ordering_confirmation(order_summary)
    hitl_expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    await _log(run_id, "ordering", "node_complete", {
        "order_summary": order_summary,
        "ordering_agent_thread_id": ordering_agent_thread_id,
    })

    return {
        **state,
        "current_step": "ordering",
        "order_summary": order_summary,
        "ordering_messages": [],
        "ordering_agent_thread_id": ordering_agent_thread_id,
        "order_constraints": state.get("order_constraints", {}),
        "token_usage": state.get("token_usage", {}),
        "hitl_action": "place_order",
        "hitl_status": "pending",
        "hitl_prompt": hitl_prompt,
        "hitl_expires_at": hitl_expires_at,
    }


async def complaint_node(state: AgentState) -> dict:
    await _log(state["run_id"], "complaint", "node_start", {
        "message": "Analyzing customer complaint...",
    })

    from agents.complaint import run_complaint_analysis
    from core.observability import langfuse_node_span

    config = await _load_agent_config("complaint")
    complaint_text = state.get("user_message", "")
    reprompt = state.get("complaint_reprompt", "")

    # Combine original complaint with user's updated request if re-prompting.
    # Use emphatic framing so the LLM treats the updated request as a hard override.
    analysis_text = complaint_text
    if reprompt:
        analysis_text = (
            f"Original complaint: {complaint_text}\n\n"
            f"*** CUSTOMER'S UPDATED REQUEST — MUST HONOUR THIS: {reprompt} ***\n"
            f"The customer has explicitly changed their preference. "
            f"Their updated request overrides the default resolution guidelines."
        )

    resolution_result: dict = {}
    with langfuse_node_span(
        run_id=state["run_id"],
        user_id=state.get("user_id", ""),
        workflow_type=state.get("workflow_type", ""),
        node_name="complaint",
    ) as lf_callbacks:
        try:
            resolution_result = await run_complaint_analysis(analysis_text, config, callbacks=lf_callbacks)
        except Exception as exc:
            logger.warning("Complaint analysis failed: %s", exc)

    if not resolution_result:
        resolution_result = {
            "resolution_type": "compensate",
            "reason": "Unable to determine resolution automatically. Defaulting to compensation.",
            "compensation_amount": 0.0,
            "original_item": "Unknown",
            "restaurant_name": "Unknown",
            "order_id": "",
        }

    resolution_type = resolution_result.get("resolution_type", "compensate")
    reason = resolution_result.get("reason", "")
    compensation = resolution_result.get("compensation_amount", 0.0)
    item = resolution_result.get("original_item", "item")
    restaurant = resolution_result.get("restaurant_name", "restaurant")

    if resolution_type == "reorder":
        action_line = f"🔁 <b>Re-order</b> {item} from {restaurant}"
    else:
        action_line = f"💰 <b>Refund Rs{compensation:.0f}</b> to customer"

    hitl_prompt = (
        f"🚨 <b>Customer Complaint</b>\n\n"
        f"Complaint: {complaint_text}\n\n"
        f"📦 Last order: <b>{item}</b> from <b>{restaurant}</b>\n\n"
        f"🤖 Agent recommendation:\n{action_line}\n"
        f"Reason: {reason}\n\n"
        f"Reply <b>YES</b> to approve or <b>NO</b> to escalate to support."
    )

    hitl_expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    await _log(state["run_id"], "complaint", "node_complete", {
        "resolution_result": resolution_result,
    })

    return {
        **state,
        "current_step": "complaint",
        "resolution_result": resolution_result,
        "complaint_reprompt": "",  # consumed — clear for next run
        "hitl_action": "resolve_complaint",
        "hitl_status": "pending",
        "hitl_prompt": hitl_prompt,
        "hitl_expires_at": hitl_expires_at,
    }


def _format_food_ordering_confirmation(order_summary: dict) -> str:
    """Telegram HITL prompt shown right after ordering, before fraud/payment."""
    if not order_summary or order_summary.get("no_match"):
        reason = order_summary.get("reason", "No restaurants match your criteria.") if order_summary else "No results found."
        return (
            "❌ <b>No matching restaurant found</b>\n\n"
            f"{reason}\n\n"
            "Please describe what you'd like differently, or reply <b>NO</b> to cancel."
        )
    return (
        f"🍽 <b>Order Confirmation</b>\n\n"
        f"Restaurant: <b>{order_summary.get('restaurant_name', 'N/A')}</b>"
        + (f" ★ {order_summary.get('rating', '')}" if order_summary.get("rating") else "") + "\n"
        f"Item: <b>{order_summary.get('item_name', 'N/A')}</b>\n"
        f"Price: Rs{order_summary.get('price', 'N/A')}\n"
        f"Cuisine: {order_summary.get('cuisine', 'N/A')}\n"
        f"Delivery: ~{order_summary.get('delivery_time_mins', 'N/A')} min\n\n"
        f"Reply <b>YES</b> to confirm this order.\n"
        f"Reply <b>NO</b> to cancel.\n"
        f"Or describe what you'd like differently."
    )


async def fraud_node(state: AgentState) -> dict:
    await _log(state["run_id"], "fraud", "node_start", {
        "message": "Running fraud check...",
    })

    order_summary = state.get("order_summary") or {}
    payment_result_prev = state.get("payment_result") or {}
    amount = float(
        order_summary.get("price")
        or payment_result_prev.get("base_amount")
        or 0.0
    )
    user_id = state.get("user_id") or None

    fraud_result: dict = {"decision": "approve", "fraud_score": 10, "triggered_rules": [], "reasoning": "default"}
    try:
        tools = await get_mcp_tools(["fraud_scoring"])
        fraud_tool = next((t for t in tools if t.name == "fraud_scoring"), None)
        if fraud_tool:
            raw = await fraud_tool.ainvoke({"amount": amount, "user_id": user_id})
            if isinstance(raw, dict):
                fraud_result = raw
            elif isinstance(raw, str):
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    fraud_result = parsed
    except Exception as exc:
        logger.warning("fraud_scoring tool error: %s", exc)

    await _log(state["run_id"], "fraud", "node_complete", {
        "fraud_result": fraud_result,
        "tokens": {},
    })

    return {
        **state,
        "current_step": "fraud",
        "fraud_result": fraud_result,
    }


async def payment_node(state: AgentState) -> dict:
    await _log(state["run_id"], "payment", "node_start", {
        "message": "Selecting payment gateway...",
    })

    order_summary = state.get("order_summary") or {}
    amount = float(order_summary.get("price") or 0.0)
    failed_gateway = (state.get("payment_result") or {}).get("gateway_name") or None

    payment_result: dict = {}
    try:
        tools = await get_mcp_tools(["payment_routing"])
        payment_tool = next((t for t in tools if t.name == "payment_routing"), None)
        if payment_tool:
            raw = await payment_tool.ainvoke({"amount": amount, "exclude_gateway": failed_gateway})
            options: list = []
            if isinstance(raw, list):
                options = raw
            elif isinstance(raw, str):
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    options = parsed
                elif isinstance(parsed, dict):
                    options = [parsed]
            if options:
                payment_result = options[0]
    except Exception as exc:
        logger.warning("payment_routing tool error: %s", exc)

    if not payment_result:
        payment_result = {
            "gateway_name": "Razorpay", "method": "UPI", "success_rate": 97.0,
            "fee_percent": 1.5, "fee_amount": round(amount * 0.015, 2),
            "total_amount": round(amount * 1.015, 2), "base_amount": amount,
        }

    await _log(state["run_id"], "payment", "node_complete", {
        "payment_result": payment_result,
        "tokens": {},
    })

    result: dict = {
        **state,
        "current_step": "payment",
        "payment_result": payment_result,
    }

    return result


async def hitl_node(state: AgentState) -> dict:
    """Human-in-the-loop checkpoint using LangGraph interrupt().

    Surfaces the interrupt to the user then routes based on the decision:
      - approved → confirmed, continue to fraud/payment/notification
      - rejected (NO/CANCEL) → rejected, route to END or notification
      - correction/reprompt text → route back to ordering or complaint node
    """
    await _log(state["run_id"], "hitl", "node_start", {
        "message": "Waiting for human confirmation...",
        "hitl_action": state.get("hitl_action"),
    })

    expires_at_str = state.get("hitl_expires_at", "")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(timezone.utc) > expires_at:
                await _log(state["run_id"], "hitl", "node_complete", {"hitl_status": "expired"})
                return {**state, "current_step": "hitl", "hitl_status": "expired"}
        except ValueError:
            pass

    decision = interrupt({
        "hitl_prompt": state.get("hitl_prompt", ""),
        "hitl_action": state.get("hitl_action", ""),
    })

    approved = decision.get("approved", False)
    raw_response = decision.get("raw_response", "")

    # Complaint re-prompt: user wants to change their resolution (e.g. "I want compensation instead")
    if (
        not approved
        and state.get("workflow_type") == "complaint_resolution"
        and state.get("hitl_action") == "resolve_complaint"
        and decision.get("reprompt", False)
    ):
        await _log(state["run_id"], "hitl", "node_complete", {
            "hitl_status": "reprompt",
            "complaint_reprompt": raw_response,
        })
        return {
            **state,
            "current_step": "hitl",
            "hitl_status": "reprompt",
            "complaint_reprompt": raw_response,
            "resolution_result": None,
            "fraud_result": None,
            "workflow_status": "running",
        }

    # Food ordering correction: route back to ordering_node which resumes the inner
    # agent with Command(resume={"decisions": [{"type": "reject", "message": correction}]})
    if (
        not approved
        and state.get("workflow_type") == "food_ordering"
        and raw_response.upper() not in ("NO", "N", "CANCEL", "REJECT", "STOP", "")
    ):
        correction = (
            "Please suggest different options. You may relax the price constraint slightly if needed."
            if raw_response.lower() in ("show_other_options", "other options", "show other options")
            else raw_response
        )
        await _log(state["run_id"], "hitl", "node_complete", {
            "hitl_status": "retry_order",
            "correction": correction,
        })
        return {
            **state,
            "current_step": "hitl",
            "hitl_status": "retry_order",
            "hitl_response": correction,
            "order_summary": None,
            "fraud_result": None,
            "payment_result": None,
            "workflow_status": "running",
        }

    # Complaint confirmed + reorder: set user_message and clear ordering state so
    # ordering_node runs a fresh search for the replacement food item.
    if (
        approved
        and state.get("workflow_type") == "complaint_resolution"
        and state.get("hitl_action") == "resolve_complaint"
    ):
        resolution = state.get("resolution_result") or {}
        if resolution.get("resolution_type") == "reorder":
            item = resolution.get("original_item", "item")
            restaurant = resolution.get("restaurant_name", "restaurant")
            # Build a rich ordering query so the agent searches for the right thing.
            # Include original complaint text so the ordering agent has full context
            # (e.g. city, cuisine) even if the resolution fields missed something.
            original_complaint = state.get("user_message", "")
            ordering_query = (
                f"I need to order {item} from {restaurant}. "
                f"Context: {original_complaint}"
            )
            await _log(state["run_id"], "hitl", "node_complete", {
                "hitl_status": "confirmed",
                "hitl_response": raw_response,
            })
            return {
                **state,
                "current_step": "hitl",
                "hitl_status": "confirmed",
                "hitl_response": raw_response,
                "user_message": ordering_query,
                "ordering_agent_thread_id": "",
                "order_summary": None,
                "workflow_status": "running",
            }

    hitl_status = "confirmed" if approved else "rejected"

    await _log(state["run_id"], "hitl", "node_complete", {
        "hitl_status": hitl_status,
        "hitl_response": raw_response,
    })

    return {
        **state,
        "current_step": "hitl",
        "hitl_status": hitl_status,
        "hitl_response": raw_response,
        "workflow_status": "cancelled" if hitl_status in ("rejected", "expired") else state.get("workflow_status", "running"),
    }


async def notification_node(state: AgentState) -> dict:
    await _log(state["run_id"], "notification", "node_start", {
        "message": "Sending notification...",
    })

    chat_id = state.get("telegram_chat_id", "")
    message = _build_notification_message(state)

    if chat_id:
        try:
            import os
            from telegram import Bot
            token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            if token:
                bot = Bot(token=token)
                await bot.send_message(
                    chat_id=int(chat_id),
                    text=message,
                    parse_mode="HTML",
                )
                logger.info("Telegram notification sent to chat_id=%s", chat_id)
            else:
                logger.warning("TELEGRAM_BOT_TOKEN not set — skipping Telegram send")
        except Exception as exc:
            logger.warning("Failed to send Telegram notification: %s", exc)
    else:
        logger.info("No telegram_chat_id — skipping Telegram notification")

    await _log(state["run_id"], "notification", "node_complete", {
        "notification_sent": bool(chat_id),
        "message": message,
    })

    return {
        **state,
        "current_step": "notification",
        "workflow_status": "completed",
    }


def _build_notification_message(state: AgentState) -> str:
    hitl_status = state.get("hitl_status", "")
    workflow_type = state.get("workflow_type", "")
    fraud_result = state.get("fraud_result") or {}
    order_summary = state.get("order_summary") or {}
    payment_result = state.get("payment_result") or {}

    # Fraud blocked
    if fraud_result.get("decision") == "block":
        score = fraud_result.get("fraud_score", 0)
        return f"🚫 Order blocked: fraud risk detected (score: {score}/100)."

    if workflow_type == "food_ordering":
        if hitl_status == "confirmed":
            payment_line = ""
            if payment_result.get("gateway_name"):
                payment_line = (
                    f" Paid Rs{payment_result.get('total_amount', order_summary.get('price', 0))} "
                    f"via {payment_result.get('gateway_name')} {payment_result.get('method', '')}."
                )
            return (
                f"✅ Order confirmed! "
                f"{order_summary.get('restaurant_name', 'Restaurant')} — "
                f"{order_summary.get('item_name', 'Item')} "
                f"Rs{order_summary.get('price', 0)}. "
                f"~{order_summary.get('delivery_time_mins', '?')} mins delivery."
                f"{payment_line}"
            )
        if hitl_status == "rejected":
            return "❌ Order cancelled."
        if hitl_status == "expired":
            return "⏰ Your session expired. Please try again."

    if workflow_type == "complaint_resolution":
        resolution = state.get("resolution_result") or {}
        resolution_type = resolution.get("resolution_type", "compensate")
        hitl_action = state.get("hitl_action", "")

        if hitl_action == "place_order":
            # Complaint reorder: food search + confirmation just completed
            if hitl_status == "confirmed":
                order = state.get("order_summary") or {}
                item = order.get("item_name") or resolution.get("original_item", "your item")
                restaurant = order.get("restaurant_name") or resolution.get("restaurant_name", "the restaurant")
                delivery = order.get("delivery_time_mins", "?")
                return (
                    f"✅ Fresh order placed!\n"
                    f"{item} from {restaurant}. "
                    f"Estimated delivery: ~{delivery} mins."
                )
            return "Order search cancelled. Please contact support if you need further assistance."

        if hitl_status == "confirmed":
            if resolution_type == "reorder":
                # Fallback: reorder confirmed but ordering node didn't run
                return (
                    f"✅ Your complaint has been resolved!\n"
                    f"We're re-ordering {resolution.get('original_item', 'your item')} "
                    f"from {resolution.get('restaurant_name', 'the restaurant')}. "
                    f"It will arrive shortly."
                )
            amount = resolution.get("compensation_amount", 0)
            return (
                f"✅ Your complaint has been resolved!\n"
                f"A refund of Rs{amount:.0f} will be processed within 2 business hours. "
                f"We apologise for the inconvenience."
            )
        if hitl_status == "rejected":
            return "Your complaint has been escalated to our support team. We'll contact you shortly."
        if hitl_status == "expired":
            return "⏰ Your session expired. Please contact support directly."

    return "ℹ️ Workflow completed."



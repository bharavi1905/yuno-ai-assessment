"""
Telegram bot — handles incoming messages and HITL (Human-in-the-Loop) flow.

Flow:
  1. User sends food order request  → trigger food_ordering graph
  2. Graph runs until hitl_node interrupt() → bot sends confirmation summary
  3. User replies YES/NO             → graph resumes via Command(resume=...)
  4. notification_node sends result  → bot sends final message

HITL session is stored in Redis at telegram:session:{chat_id} with 10-min TTL.
thread_id == str(chat_id) — enforced invariant for LangGraph checkpoint resume.
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from langgraph.types import Command

from core.config import settings
from core.redis_client import redis_client

logger = logging.getLogger(__name__)

# Module-level application — initialised in start_bot()
_application: Optional[Application] = None

HITL_TTL_SECONDS = 600  # 10 minutes

# ── Redis session helpers ─────────────────────────────────────────────────────

async def _save_session(chat_id: str, data: dict) -> None:
    key = f"telegram:session:{chat_id}"
    await redis_client.setex(key, HITL_TTL_SECONDS, json.dumps(data))


async def _get_session(chat_id: str) -> Optional[dict]:
    key = f"telegram:session:{chat_id}"
    raw = await redis_client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def _clear_session(chat_id: str) -> None:
    await redis_client.delete(f"telegram:session:{chat_id}")


# ── Graph invocation helpers ──────────────────────────────────────────────────

def _make_config(chat_id: str) -> dict:
    """LangGraph config — thread_id must equal chat_id for HITL resume."""
    return {"configurable": {"thread_id": str(chat_id)}}


async def _invoke_graph(workflow_type: str, chat_id: str, initial_state: dict) -> dict:
    from graph.builder import get_graph
    graph = get_graph(workflow_type)
    config = _make_config(chat_id)
    result = await graph.ainvoke(initial_state, config=config)
    return result


async def _resume_graph(workflow_type: str, chat_id: str, approved: bool, raw: str, reprompt: bool = False) -> dict:
    from graph.builder import get_graph
    graph = get_graph(workflow_type)
    config = _make_config(chat_id)
    result = await graph.ainvoke(
        Command(resume={"approved": approved, "raw_response": raw, "reprompt": reprompt}),
        config=config,
    )
    return result


async def _reply(update: Update, text: str, parse_mode: str = "HTML") -> None:
    """Send a reply with one automatic retry on transient network errors."""
    for attempt in range(2):
        try:
            await update.message.reply_text(text, parse_mode=parse_mode)
            return
        except (NetworkError, TimedOut) as e:
            if attempt == 0:
                logger.warning("Transient Telegram send error, retrying: %s", e)
                await asyncio.sleep(2)
            else:
                logger.error("Failed to send Telegram message after retry: %s", e)


# ── Message handlers ──────────────────────────────────────────────────────────

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(
        update,
        "Welcome to the <b>Workflow Assistant</b>!\n\n"
        "Send me a food order request or report a complaint, for example:\n"
        "  <code>Order chicken biryani under Rs300, 4+ stars, Hyderabad</code>\n"
        "  <code>I got the wrong item — I ordered chicken biryani but received veg biryani</code>",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    text = update.message.text.strip()

    # Check if there's an active HITL session waiting for a reply
    session = await _get_session(chat_id)
    if session and session.get("hitl_status") == "pending":
        await handle_hitl_reply(update, context, session, text)
        return

    # New workflow trigger
    await handle_new_workflow(update, context, chat_id, text)


async def handle_new_workflow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    text: str,
) -> None:
    run_id = str(uuid.uuid4())
    await _reply(update, "Processing your request... Please wait.", parse_mode=None)

    intent = await _classify_intent(text)
    workflow_type = "complaint_resolution" if intent == "complaint" else "food_ordering"

    initial_state = {
        "run_id": run_id,
        "workflow_type": workflow_type,
        "telegram_chat_id": chat_id,
        "user_id": chat_id,
        "messages": [{"role": "user", "content": text}],
        "user_message": text,
        "current_step": "router",
        "workflow_status": "running",
        "execution_logs": [],
        "error": None,
        "order_constraints": _parse_order_constraints(text),
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
        "hitl_action": "resolve_complaint" if workflow_type == "complaint_resolution" else "place_order",
        "token_usage": {},
    }

    try:
        result = await _invoke_graph(workflow_type, chat_id, initial_state)
    except Exception as e:
        logger.exception("Graph invocation failed for chat_id=%s", chat_id)
        await _reply(update, f"Sorry, something went wrong: {e}", parse_mode=None)
        return

    await _handle_graph_result(update, chat_id, result, workflow_type, run_id)


async def handle_hitl_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: dict,
    text: str,
) -> None:
    chat_id = str(update.effective_chat.id)
    workflow_type = session.get("workflow_type", "food_ordering")
    hitl_action = session.get("hitl_action", "")
    run_id = session.get("active_run_id", "")

    # Check session expiry
    expires_at_str = session.get("hitl_expires_at", "")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", ""))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                await _clear_session(chat_id)
                await update.message.reply_text(
                    "Your session has expired. Please send a new request."
                )
                return
        except ValueError:
            pass

    upper = text.strip().upper()
    approved = upper in ("YES", "Y", "CONFIRM", "OK", "PROCEED")
    is_simple_no = upper in ("NO", "N", "CANCEL", "REJECT", "STOP", "ESCALATE")

    # "Show other options" only for food ordering
    if (
        any(kw in upper for kw in ("OTHER", "MORE", "ALTERNATIVES", "OPTIONS"))
        and workflow_type == "food_ordering"
    ):
        await handle_relaxed_retry(update, context, session, chat_id)
        return

    # Complaint re-prompt: user typed something that's not YES/NO/escalate during
    # the resolve_complaint HITL — treat it as a request to change the resolution.
    if (
        workflow_type == "complaint_resolution"
        and hitl_action == "resolve_complaint"
        and not approved
        and not is_simple_no
    ):
        await _reply(update, "Updating your request...", parse_mode=None)
        try:
            result = await _resume_graph(workflow_type, chat_id, False, text, reprompt=True)
        except Exception as e:
            logger.exception("Complaint reprompt failed for chat_id=%s", chat_id)
            await _clear_session(chat_id)
            await _reply(update, f"Sorry, something went wrong: {e}", parse_mode=None)
            return
        await _clear_session(chat_id)
        await _handle_graph_result(update, chat_id, result, workflow_type, run_id)
        return

    await _reply(update, "Processing your response...", parse_mode=None)

    try:
        result = await _resume_graph(workflow_type, chat_id, approved, text)
    except Exception as e:
        logger.exception("Graph resume failed for chat_id=%s", chat_id)
        await _clear_session(chat_id)
        await _reply(update, f"Sorry, something went wrong: {e}", parse_mode=None)
        return

    await _clear_session(chat_id)
    await _handle_graph_result(update, chat_id, result, workflow_type, run_id)


async def handle_relaxed_retry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: dict,
    chat_id: str,
) -> None:
    """Re-run the ordering node with relaxed price constraints (+Rs50)."""
    workflow_type = session.get("workflow_type", "food_ordering")
    run_id = session.get("active_run_id", str(uuid.uuid4()))

    await _reply(update, "Let me search for more options...", parse_mode=None)

    # Resume with a special signal that tells the ordering node to relax constraints
    try:
        result = await _resume_graph(workflow_type, chat_id, False, "show_other_options")
    except Exception as e:
        logger.exception("Relaxed retry failed for chat_id=%s", chat_id)
        await _clear_session(chat_id)
        await _reply(update, f"Sorry, could not find more options: {e}", parse_mode=None)
        return

    await _handle_graph_result(update, chat_id, result, workflow_type, run_id)


async def _handle_graph_result(
    update: Update,
    chat_id: str,
    result: dict,
    workflow_type: str,
    run_id: str,
) -> None:
    """Inspect graph result and send appropriate Telegram reply."""
    hitl_status = result.get("hitl_status", "not_required")
    workflow_status = result.get("workflow_status", "completed")

    if hitl_status == "pending":
        # Graph paused at interrupt() — send HITL prompt to user
        hitl_prompt = result.get("hitl_prompt", "Please confirm to proceed.")
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=HITL_TTL_SECONDS)
        ).isoformat()

        await _save_session(chat_id, {
            "active_run_id": run_id,
            "hitl_status": "pending",
            "hitl_expires_at": expires_at,
            "workflow_type": workflow_type,
            "hitl_action": result.get("hitl_action", ""),
        })

        await _reply(update, hitl_prompt)
        return

    # notification_node already sent the Telegram message for completed workflows.
    if workflow_status == "completed":
        return

    error = result.get("error")
    if error:
        await _reply(update, f"Workflow failed: {error}", parse_mode=None)
        return

    # Cancelled / rejected / expired — notification_node did NOT run, send message here.
    msg = _build_completion_message(result, workflow_type)
    await _reply(update, msg, parse_mode=None)


def _build_completion_message(result: dict, workflow_type: str) -> str:
    hitl_status = result.get("hitl_status", "")
    hitl_action = result.get("hitl_action", "")

    if hitl_status == "rejected":
        if hitl_action == "place_order":
            return "Order cancelled. Send a new message when you're ready to order."
        if hitl_action == "resolve_complaint":
            return "Your complaint has been escalated to our support team. We'll contact you shortly."
        return "Recovery cancelled. Your order is on hold."

    if workflow_type == "food_ordering":
        order = result.get("order_summary") or {}
        payment = result.get("payment_result") or {}
        fraud = result.get("fraud_result") or {}

        if fraud.get("decision") == "block":
            return (
                "Your order could not be processed — our fraud checks flagged this "
                "transaction. Please try again or contact support."
            )

        restaurant = order.get("restaurant_name", "your restaurant")
        item = order.get("item_name", "your item")
        price = order.get("price", 0)
        delivery = order.get("delivery_time_mins", "?")
        gw = payment.get("gateway", "")
        method = payment.get("method", "")

        return (
            f"Order confirmed!\n\n"
            f"Restaurant: {restaurant}\n"
            f"Item: {item}\n"
            f"Price: Rs{price}\n"
            f"Estimated delivery: ~{delivery} mins\n"
            f"Payment: {gw} {method}\n\n"
            "Your order has been placed successfully."
        )

    return "Workflow completed successfully."


_INTENT_PROMPT = """Classify this customer message into exactly one category:
- food_order: user wants to place a new food order
- complaint: user is reporting a problem with a past/existing order (wrong item, missing item, quality issue, damaged, late delivery, etc.)

Message: "{text}"

Reply with only the category name, nothing else."""


async def _classify_intent(text: str) -> str:
    """Use LLM to classify message intent. Returns 'food_order' or 'complaint'."""
    from langchain_openai import ChatOpenAI
    try:
        model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        result = await model.ainvoke(_INTENT_PROMPT.format(text=text))
        intent = result.content.strip().lower()
        if intent in ("food_order", "complaint"):
            return intent
        logger.warning("Unexpected intent classification '%s', defaulting to food_order", intent)
        return "food_order"
    except Exception as exc:
        logger.warning("Intent classification failed (%s), defaulting to food_order", exc)
        return "food_order"


def _parse_order_constraints(text: str) -> dict:
    """Extract basic constraints from free-text order message."""
    import re
    constraints: dict = {}

    # Price: "under Rs300", "below 300", "less than Rs 300"
    price_match = re.search(r"(?:under|below|less than|upto|up to)\s*(?:rs\.?\s*)?(\d+)", text, re.IGNORECASE)
    if price_match:
        constraints["max_price"] = float(price_match.group(1))

    # Rating: "4+ stars", "4.5 stars", "rating 4"
    rating_match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*stars?", text, re.IGNORECASE)
    if rating_match:
        constraints["min_rating"] = float(rating_match.group(1))

    # City: look for known cities
    cities = ["bangalore", "mumbai", "delhi", "hyderabad", "chennai"]
    for city in cities:
        if city in text.lower():
            constraints["city"] = city.capitalize()
            break

    # Cuisine hint from keywords
    cuisine_keywords = {
        "biryani": "Biryani",
        "south indian": "South Indian",
        "north indian": "North Indian",
        "mughlai": "Mughlai",
        "seafood": "Seafood",
        "chettinad": "Chettinad",
    }
    for keyword, cuisine in cuisine_keywords.items():
        if keyword in text.lower():
            constraints["cuisine"] = cuisine
            break

    constraints["raw_query"] = text
    return constraints


async def _send_message(chat_id: str, text: str, parse_mode: str = "HTML") -> None:
    """Send a message via the running bot application."""
    if _application is None:
        logger.warning("Bot not running — cannot send message to %s", chat_id)
        return
    for attempt in range(2):
        try:
            await _application.bot.send_message(chat_id=int(chat_id), text=text, parse_mode=parse_mode)
            return
        except (NetworkError, TimedOut) as e:
            if attempt == 0:
                logger.warning("Transient send error to %s, retrying: %s", chat_id, e)
                await asyncio.sleep(2)
            else:
                logger.error("Failed to send message to %s after retry: %s", chat_id, e)


# ── Lifecycle ─────────────────────────────────────────────────────────────────

async def start_bot() -> None:
    """Build and start the Telegram bot using non-blocking async polling."""
    global _application

    token = settings.telegram_bot_token
    if not token or token.startswith("your_") or token == "":
        logger.warning(
            "TELEGRAM_BOT_TOKEN not configured — Telegram bot disabled."
        )
        return

    _application = (
        Application.builder()
        .token(token)
        .build()
    )

    async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.warning("Telegram handler error: %s", context.error)

    _application.add_handler(CommandHandler("start", handle_start))
    _application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    _application.add_error_handler(_error_handler)

    try:
        await _application.initialize()
        await _application.start()
        # start_polling() is non-blocking — runs in background
        await _application.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started and polling.")
    except Exception as e:
        logger.warning("Telegram bot could not start (%s) — bot disabled.", e)
        _application = None


async def stop_bot() -> None:
    """Gracefully stop the Telegram bot."""
    global _application
    if _application is None:
        return
    await _application.updater.stop()
    await _application.stop()
    await _application.shutdown()
    _application = None
    logger.info("Telegram bot stopped.")

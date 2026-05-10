"""Ordering agent: restaurant search with HumanInTheLoopMiddleware.

The agent calls restaurant_search + menu_retrieval (MCP tools), then calls
confirm_order when it has found the best match. HumanInTheLoopMiddleware
intercepts the confirm_order call and fires interrupt() before executing it,
pausing the agent until the human approves or provides feedback.

Resume decisions:
  Approve:  Command(resume={"decisions": [{"type": "approve"}]})
  Reject:   Command(resume={"decisions": [{"type": "reject", "message": "..."}]})
"""

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from agents.base import get_mcp_tools

ORDERING_TOOLS = ["restaurant_search", "menu_retrieval"]

ORDERING_SYSTEM = """You are a restaurant search specialist for Indian cities.

WORKFLOW (follow exactly, in order):
1. Call restaurant_search ONCE with the user's constraints:
   - city (required — extract from user message)
   - restaurant_name (if the user names a specific restaurant, e.g. "from Paradise")
   - cuisine (the food type or dish name, e.g. "biryani", "chicken biryani")
   - max_price (if a budget is mentioned, e.g. "under Rs300" → max_price=300)
   - min_rating (if a rating threshold is mentioned, e.g. "4+ stars" → min_rating=4)
2. Review the returned results and pick the single best match.
   If you need to verify a specific dish exists, call menu_retrieval(restaurant_id) for ONE restaurant only.
3. Call confirm_order with all details of your chosen match to present it for human approval.

AFTER confirm_order:
- If approved: output "Order confirmed."
- If rejected with feedback: re-search and call confirm_order again with the new best option.
  CRITICAL — if the feedback says "different restaurant", "another restaurant", "not this one",
  or names a specific restaurant: you MUST NOT recommend the same restaurant again.
  Look at ALL results from restaurant_search and pick one that is NOT the restaurant you just showed.
  If the feedback names a specific restaurant (e.g. "order from Paradise"), use restaurant_name=that name in your search.
  If feedback names a restaurant that is not found, call confirm_order with no_match=True explaining it is not available.

PARAMETER EXTRACTION EXAMPLES:
- "biryani from Paradise, Hyderabad" → city="Hyderabad", restaurant_name="Paradise", cuisine="biryani"
- "chicken biryani under Rs300, 4+ stars, Bangalore" → city="Bangalore", cuisine="chicken biryani", max_price=300, min_rating=4
- "paneer dish in Mumbai" → city="Mumbai", cuisine="paneer"

HARD RULES:
- Call restaurant_search EXACTLY ONCE per search attempt.
- Call menu_retrieval AT MOST ONCE per search attempt.
- ALWAYS call confirm_order when you have a result — never output it as plain text.
- If no restaurants match, call confirm_order with no_match=True and explain why in reason."""


@tool
def confirm_order(
    restaurant_name: str = "",
    item_name: str = "",
    price: float = 0.0,
    rating: float = 0.0,
    delivery_time_mins: int = 30,
    cuisine: str = "",
    city: str = "",
    restaurant_id: str = "",
    no_match: bool = False,
    reason: str = "",
) -> str:
    """Present the selected restaurant and item to the user for order confirmation.

    Call this when you have found the best match and are ready to confirm.
    HumanInTheLoopMiddleware will intercept this call and ask the human before
    the tool actually executes.

    For no-match situations, set no_match=True and reason="why no restaurants found".
    """
    if no_match:
        return f"No match reported to user: {reason}. Awaiting feedback."
    return (
        f"Order confirmation requested: {restaurant_name} — {item_name} "
        f"@ Rs{price}. Awaiting human decision."
    )


async def build_ordering_agent(config: dict, checkpointer=None):
    """Build ordering agent using create_agent + HumanInTheLoopMiddleware.

    The middleware intercepts confirm_order before execution, firing interrupt()
    so a human can approve or redirect. The checkpointer is required for the
    agent to persist its state across the interrupt.

    Args:
        config: Agent config dict (model, etc.)
        checkpointer: LangGraph checkpointer (AsyncPostgresSaver) shared with the
            outer graph. Enables the inner agent to resume after a HITL decision.
    """
    mcp_tools = await get_mcp_tools(ORDERING_TOOLS)
    all_tools = mcp_tools + [confirm_order]
    model_name = config.get("model", "gpt-4o-mini").replace("openai:", "")
    model = ChatOpenAI(model=model_name, temperature=0)

    return create_agent(
        model=model,
        tools=all_tools,
        system_prompt=ORDERING_SYSTEM,
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={"confirm_order": True},
            )
        ],
        checkpointer=checkpointer,
    )

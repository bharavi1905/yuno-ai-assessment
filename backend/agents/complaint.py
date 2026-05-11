"""Complaint agent: looks up the last order and decides resolution.

Two-step chain:
  Step 1: call order_lookup MCP tool to get order details
  Step 2: model.with_structured_output(ResolutionResult) to decide resolution
No HumanInTheLoopMiddleware — HITL happens at outer graph level via hitl_node.
"""
import json
import logging

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agents.base import get_mcp_tools

logger = logging.getLogger(__name__)

COMPLAINT_TOOLS = ["order_lookup"]


def _parse_mcp_result(raw) -> dict:
    """Parse MCP tool result which may be a dict, JSON string, or list of content blocks."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    if isinstance(raw, list):
        # langchain-mcp-adapters returns [{"type": "text", "text": "{...json...}"}]
        for block in raw:
            text = block.get("text", "") if isinstance(block, dict) else str(block)
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue
    return {}

COMPLAINT_SYSTEM = """You are a customer service specialist for a food delivery platform.

A customer has reported a problem with their order.

== EXTRACTION RULES (read first) ==
original_item: Extract ONLY from the customer's complaint text — what they say they WANTED to order.
  Example: "I ordered chicken biryani but got veg biryani" → original_item = "chicken biryani"
  Do NOT use the system order data for this field.

restaurant_name: Use the restaurant the customer explicitly states they want.
  - If the customer's UPDATED REQUEST mentions a restaurant → use that (it overrides the original complaint).
  - Else if the customer's original complaint mentions a restaurant → use that.
  - Fall back to the system order data only if the customer never mentioned a restaurant.
  - Examples: "reorder from Paradise" → "Paradise"; "from Ohri" → "Ohri".

order_id: Always take from the system order data.
compensation_amount: Calculate from the system order amount.

== RESOLUTION ==
Decide the best resolution:
  - "reorder": wrong item or missing item → re-order the correct item the customer wanted
  - "compensate": quality issue, late delivery, or restaurant closed → issue a refund

RESOLUTION GUIDELINES:
- Wrong item received → prefer "reorder" the correct item, else "compensate" full amount
- Customer requests specific restaurant for reorder → honour that request
- Missing item → "compensate" for the missing item amount
- Cold/quality issue → "compensate" 50% of order amount
- Very late delivery → "compensate" 20% credit

OVERRIDE RULE — HIGHEST PRIORITY:
If the customer's updated request explicitly asks for a refund, compensation, or money back
(e.g. "I'd prefer refund", "give me my money back", "compensate me", "I want compensation"),
resolution_type MUST be "compensate". The customer's stated preference always overrides the
default recommendation guidelines above.

Always include a clear, customer-friendly reason for your decision.
compensation_amount is the INR refund/credit amount (0 if resolution_type is reorder).
"""


class ResolutionResult(BaseModel):
    resolution_type: str = Field(description="reorder or compensate")
    reason: str = Field(description="Clear explanation of the resolution decision")
    compensation_amount: float = Field(default=0.0, description="Refund/credit in INR, 0 if reorder")
    original_item: str = Field(description="The item the customer says they WANTED to order — extract from their complaint text, NOT from the system delivered item")
    restaurant_name: str = Field(description="Restaurant the customer wants — use what they explicitly state in their complaint or updated request; fall back to system data only if they never mentioned one")
    order_id: str = Field(default="", description="Order ID from system lookup")


async def build_complaint_agent(config: dict) -> ChatOpenAI:
    model_name = config.get("model", "gpt-4o-mini").replace("openai:", "")
    return ChatOpenAI(model=model_name, temperature=0)


async def run_complaint_analysis(
    complaint_text: str,
    config: dict,
    callbacks: list | None = None,
) -> dict:
    """Run the two-step complaint analysis chain.

    Step 1: Call order_lookup via MCP tool to get order details.
    Step 2: Feed order details + complaint into structured output model.
    Returns a dict matching ResolutionResult fields.
    callbacks: optional LangChain callbacks (e.g. Langfuse) forwarded to the LLM call.
    """
    model_name = config.get("model", "gpt-4o-mini").replace("openai:", "")
    model = ChatOpenAI(model=model_name, temperature=0)

    # Step 1: get order details via MCP tool
    order_data: dict = {}
    try:
        tool_names = config.get("tools") or COMPLAINT_TOOLS
        mcp_tools = await get_mcp_tools(tool_names)
        order_tool = next((t for t in mcp_tools if t.name == "order_lookup"), None)
        if order_tool:
            raw = await order_tool.ainvoke({})
            order_data = _parse_mcp_result(raw)
    except Exception as exc:
        logger.warning("order_lookup tool call failed: %s", exc)

    # Step 2: structured resolution decision
    system_prompt = config.get("system_prompt") or COMPLAINT_SYSTEM
    step2_prompt = f"""{system_prompt}

Customer complaint: {complaint_text}

System lookup — what was actually delivered (may be the WRONG item):
- Delivered item (wrong): {order_data.get('item_name', 'Unknown')}
- Delivered by restaurant: {order_data.get('restaurant_name', 'Unknown')}
- Amount charged: Rs{order_data.get('amount', 0)}
- Order status: {order_data.get('status', 'unknown')}
- Order ID: {order_data.get('order_id', '')}

IMPORTANT: original_item must be what the customer says they ordered (from the complaint text above), \
NOT the delivered item shown in system data.
restaurant_name must be from what the customer explicitly states they want, NOT the delivered restaurant \
unless the customer never mentioned one.

Decide the appropriate resolution."""

    structured_model = model.with_structured_output(ResolutionResult)
    invoke_config = {"run_name": "complaint-agent", "callbacks": callbacks} if callbacks else {"run_name": "complaint-agent"}
    result: ResolutionResult = await structured_model.ainvoke(step2_prompt, config=invoke_config or None)

    result_dict = result.model_dump()

    def _is_blank(val: str) -> bool:
        return not val or val.lower() in ("unknown", "n/a", "")

    # Fill in order fields from lookup if the LLM left them blank or wrote "Unknown"
    if _is_blank(result_dict.get("order_id", "")) and order_data.get("order_id"):
        result_dict["order_id"] = order_data["order_id"]
    if _is_blank(result_dict.get("original_item", "")) and order_data.get("item_name"):
        result_dict["original_item"] = order_data["item_name"]
    if _is_blank(result_dict.get("restaurant_name", "")) and order_data.get("restaurant_name"):
        result_dict["restaurant_name"] = order_data["restaurant_name"]

    return result_dict

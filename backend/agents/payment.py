from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agents.base import get_mcp_tools

PAYMENT_TOOLS = ["payment_routing"]

PAYMENT_PROMPT = """You are a payment routing specialist.
Call the payment_routing tool with the order amount from the message.
Select the best gateway (highest success rate, lowest fee).
Return ONLY a JSON object with these exact fields:
{"gateway_name": "string", "method": "string", "success_rate": float, "fee_percent": float,
"fee_amount": float, "total_amount": float, "base_amount": float}
No extra text. JSON only."""


async def build_payment_agent(config: dict):
    """Build a LangGraph ReAct agent for payment routing via MCP tools."""
    tools = await get_mcp_tools(PAYMENT_TOOLS)
    model_name = config.get("model", "gpt-4o-mini").replace("openai:", "")
    model = ChatOpenAI(model=model_name, temperature=0)
    return create_react_agent(
        model=model,
        tools=tools,
        state_modifier=PAYMENT_PROMPT,
    )

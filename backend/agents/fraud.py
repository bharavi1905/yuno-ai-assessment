from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agents.base import get_mcp_tools

FRAUD_TOOLS = ["fraud_scoring"]

FRAUD_PROMPT = """You are a fraud detection specialist.
Call the fraud_scoring tool with the transaction details provided in the message.
After receiving the score, return ONLY a JSON object with these exact fields:
{"decision": "approve" or "block", "fraud_score": integer 0-100, "triggered_rules": [list of rule names], "reasoning": "brief explanation"}
Block if fraud_score >= 70. Approve otherwise. No extra text. JSON only."""


async def build_fraud_agent(config: dict):
    """Build a LangGraph ReAct agent for fraud scoring via MCP tools."""
    tools = await get_mcp_tools(FRAUD_TOOLS)
    model_name = config.get("model", "gpt-4o-mini").replace("openai:", "")
    model = ChatOpenAI(model=model_name, temperature=0)
    return create_react_agent(
        model=model,
        tools=tools,
        state_modifier=FRAUD_PROMPT,
    )

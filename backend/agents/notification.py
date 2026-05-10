from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agents.base import get_mcp_tools

NOTIFICATION_TOOLS = ["telegram_notify"]

NOTIFICATION_PROMPT = """You are a notification specialist.
Call the telegram_notify tool to send the message to the user.
Always call the tool with the chat_id and message provided. Return confirmation."""


async def build_notification_agent(config: dict):
    """Build a LangGraph ReAct agent for Telegram notifications via MCP tools."""
    tools = await get_mcp_tools(NOTIFICATION_TOOLS)
    model_name = config.get("model", "gpt-4o-mini").replace("openai:", "")
    model = ChatOpenAI(model=model_name, temperature=0)
    return create_react_agent(
        model=model,
        tools=tools,
        state_modifier=NOTIFICATION_PROMPT,
    )

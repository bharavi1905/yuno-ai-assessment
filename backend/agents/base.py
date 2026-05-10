from langchain_mcp_adapters.client import MultiServerMCPClient

# FastMCP's sse_app() exposes SSE at /sse inside the mounted sub-app.
# When mounted at /mcp, the external path is /mcp/sse.
# Use localhost to avoid Docker networking overhead for same-container calls.
MCP_SERVER_URL = "http://localhost:8000/mcp/sse"


async def get_mcp_tools(tool_names: list[str]) -> list:
    """Connect to the local FastMCP server and return LangChain tools filtered by name."""
    client = MultiServerMCPClient(
        {
            "agent-platform": {
                "url": MCP_SERVER_URL,
                "transport": "sse",
            }
        }
    )
    all_tools = await client.get_tools()
    if tool_names:
        return [t for t in all_tools if t.name in tool_names]
    return all_tools


def build_agent(config: dict):
    """Dispatch to the correct builder based on config['role'].

    NOTE: All builders are async coroutines — await the result.
    """
    from agents.ordering import build_ordering_agent
    from agents.fraud import build_fraud_agent
    from agents.payment import build_payment_agent
    from agents.notification import build_notification_agent
    from agents.complaint import build_complaint_agent

    builders = {
        "ordering":     build_ordering_agent,
        "fraud":        build_fraud_agent,
        "payment":      build_payment_agent,
        "notification": build_notification_agent,
        "complaint":    build_complaint_agent,
    }
    builder = builders.get(config.get("role"))
    if not builder:
        raise ValueError(f"Unknown agent role: {config.get('role')}")
    return builder(config)

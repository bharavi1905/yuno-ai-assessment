import os

import httpx

from mcp_tools.server import mcp


@mcp.tool()
def telegram_notify(chat_id: str, message: str) -> dict:
    """Send a message to a Telegram chat via the Bot API.

    Uses TELEGRAM_BOT_TOKEN from environment. Returns send status.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {"sent": False, "error": "TELEGRAM_BOT_TOKEN not configured"}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = httpx.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10.0,
        )
        response.raise_for_status()
        return {"sent": True, "chat_id": chat_id}
    except Exception as e:
        return {"sent": False, "error": str(e)}

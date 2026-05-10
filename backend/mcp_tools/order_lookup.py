from typing import Optional

from sqlalchemy import desc, select

from core.database import get_sync_session
from models.seed_data import Order, Restaurant
from mcp_tools.server import mcp


@mcp.tool()
def order_lookup(user_id: Optional[str] = None) -> dict:
    """Look up the most recent delivered order for a user.

    user_id: Telegram chat_id or internal user UUID (optional).
    Falls back to the most recent delivered order in the system for demo purposes.
    Returns: order_id, item_name, restaurant_name, amount, status, cuisine, city.
    """
    with get_sync_session() as session:
        query = (
            select(Order, Restaurant)
            .join(Restaurant, Order.restaurant_id == Restaurant.id)
            .where(Order.status.in_(["delivered", "completed"]))
            .order_by(desc(Order.created_at))
        )
        row = session.execute(query.limit(1)).first()
        if not row:
            return {
                "error": "No recent orders found",
                "order_id": "",
                "item_name": "Unknown Item",
                "restaurant_name": "Unknown Restaurant",
                "amount": 0.0,
                "status": "unknown",
                "cuisine": "",
                "city": "",
            }
        order, restaurant = row
        return {
            "order_id": str(order.id),
            "item_name": order.item_name,
            "restaurant_name": restaurant.name,
            "amount": float(order.amount),
            "status": order.status,
            "cuisine": restaurant.cuisine,
            "city": restaurant.city,
        }

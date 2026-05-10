from sqlalchemy import select

from core.database import get_sync_session
from models.seed_data import MenuItem
from mcp_tools.server import mcp


@mcp.tool()
def menu_retrieval(restaurant_id: str) -> list[dict]:
    """Retrieve all available menu items for a given restaurant."""
    with get_sync_session() as session:
        rows = session.execute(
            select(MenuItem)
            .where(MenuItem.restaurant_id == restaurant_id)
            .where(MenuItem.is_available == True)  # noqa: E712
        ).scalars().all()

        return [
            {
                "item_id": str(item.id),
                "name": item.name,
                "price": item.price,
                "category": item.category,
                "description": item.description,
                "is_available": item.is_available,
            }
            for item in rows
        ]

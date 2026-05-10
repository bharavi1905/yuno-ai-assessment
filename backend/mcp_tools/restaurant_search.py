from typing import Optional

from sqlalchemy import cast, or_, select
from sqlalchemy.sql.elements import BinaryExpression

from core.database import get_sync_session
from models.seed_data import MenuItem, Restaurant
from mcp_tools.server import mcp

_STOP_WORDS = {"the", "and", "for", "from", "with", "restaurant", "hotel", "cafe"}


def _fuzzy_name_filter(restaurant_name: str) -> BinaryExpression:
    """Token-level OR filter so slight misspellings/extra chars still match.

    "cafe bahaar"  → matches "Cafe Bahar"  (via token "cafe")
    "paradise"     → matches "Paradise Restaurant" (exact phrase)
    "bawarchi"     → matches "Bawarchi Restaurant" (exact phrase)
    """
    conditions = [Restaurant.name.ilike(f"%{restaurant_name}%")]
    tokens = [
        t for t in restaurant_name.lower().split()
        if len(t) >= 3 and t not in _STOP_WORDS
    ]
    for token in tokens:
        conditions.append(Restaurant.name.ilike(f"%{token}%"))
    return or_(*conditions)


def _embed(text: str) -> list[float]:
    from openai import OpenAI
    client = OpenAI()
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        dimensions=1536,
    )
    return response.data[0].embedding


def _has_embeddings(session) -> bool:
    try:
        return session.execute(
            select(MenuItem).where(MenuItem.embedding.is_not(None)).limit(1)
        ).scalars().first() is not None
    except Exception:
        return False


def _format_result(restaurant: Restaurant, item: MenuItem) -> dict:
    return {
        "restaurant_name": restaurant.name,
        "restaurant_id": str(restaurant.id),
        "item_name": item.name,
        "item_id": str(item.id),
        "price": item.price,
        "rating": restaurant.rating,
        "delivery_time_mins": restaurant.delivery_time_mins,
        "cuisine": restaurant.cuisine,
        "city": restaurant.city,
    }


def _deduplicate(rows, limit: int = 5) -> list[dict]:
    # rows may be (Restaurant, MenuItem) or (Restaurant, MenuItem, distance) — index 0 and 1 work for both
    seen: set[str] = set()
    results = []
    for row in rows:
        if len(results) >= limit:
            break
        restaurant, item = row[0], row[1]
        rid = str(restaurant.id)
        if rid in seen:
            continue
        seen.add(rid)
        results.append(_format_result(restaurant, item))
    return results


@mcp.tool()
def restaurant_search(
    city: str,
    cuisine: Optional[str] = None,
    restaurant_name: Optional[str] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
) -> list[dict]:
    """Search for restaurants and menu items using semantic similarity.

    cuisine: dish or food type (e.g. "chicken biryani", "paneer", "dosa")
    restaurant_name: specific restaurant to search within (e.g. "Paradise", "Bawarchi")
    max_price: maximum item price in INR
    min_rating: minimum restaurant star rating (e.g. 4.0)

    Returns up to 5 matches, one per restaurant, sorted by relevance.
    """
    from pgvector.sqlalchemy import Vector

    with get_sync_session() as session:
        if not _has_embeddings(session):
            # Embeddings not yet seeded — fall back to keyword search
            return _keyword_search(session, city, cuisine, restaurant_name, max_price, min_rating)

        # Build query text and embed it
        query_parts = [p for p in [cuisine, restaurant_name, city] if p]
        query_text = " ".join(query_parts)
        try:
            query_vec = _embed(query_text)
        except Exception:
            return _keyword_search(session, city, cuisine, restaurant_name, max_price, min_rating)

        # Cosine distance (lower = more similar)
        dist_expr = MenuItem.embedding.op("<=>")(cast(query_vec, Vector(1536)))

        query = (
            select(Restaurant, MenuItem)
            .join(MenuItem, MenuItem.restaurant_id == Restaurant.id)
            .where(Restaurant.is_active == True)   # noqa: E712
            .where(MenuItem.is_available == True)   # noqa: E712
            .where(MenuItem.embedding.is_not(None))
            .where(Restaurant.city.ilike(f"%{city}%"))
        )

        if restaurant_name:
            query = query.where(_fuzzy_name_filter(restaurant_name))
        if min_rating is not None:
            query = query.where(Restaurant.rating >= min_rating)
        if max_price is not None:
            query = query.where(MenuItem.price <= max_price)

        rows = session.execute(query.order_by(dist_expr).limit(20)).all()

    return _deduplicate(rows)


def _keyword_search(
    session,
    city: str,
    cuisine: Optional[str],
    restaurant_name: Optional[str],
    max_price: Optional[float],
    min_rating: Optional[float],
) -> list[dict]:
    """Keyword fallback used when embeddings have not been seeded yet."""
    query = (
        select(Restaurant, MenuItem)
        .join(MenuItem, MenuItem.restaurant_id == Restaurant.id)
        .where(Restaurant.is_active == True)   # noqa: E712
        .where(MenuItem.is_available == True)  # noqa: E712
        .where(Restaurant.city.ilike(f"%{city}%"))
    )

    if restaurant_name:
        query = query.where(Restaurant.name.ilike(f"%{restaurant_name}%"))

    if cuisine:
        keywords = [kw.strip() for kw in cuisine.split() if kw.strip()]
        kw_conds = []
        for kw in keywords:
            kw_conds.extend([
                MenuItem.name.ilike(f"%{kw}%"),
                MenuItem.category.ilike(f"%{kw}%"),
            ])
        query = query.where(or_(*kw_conds))

    if min_rating is not None:
        query = query.where(Restaurant.rating >= min_rating)
    if max_price is not None:
        query = query.where(MenuItem.price <= max_price)

    rows = session.execute(query.order_by(Restaurant.rating.desc()).limit(20)).all()
    return _deduplicate(rows)

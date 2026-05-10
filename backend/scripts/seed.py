"""
Data seeder — reads static JSON files from mock_data/ and inserts into PostgreSQL.
Uses sync SQLAlchemy session. Runs only if tables are empty (idempotent).
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

from core.database import get_sync_session
from models.seed_data import (
    FraudRule,
    MenuItem,
    Order,
    PaymentGateway,
    Restaurant,
    Transaction,
    User,
)
from models.agent import Agent
from models.workflow import Workflow

logger = logging.getLogger(__name__)

MOCK_DATA_DIR = Path(os.environ.get("MOCK_DATA_DIR", "/mock_data"))


def _load(filename: str) -> list[dict[str, Any]]:
    path = MOCK_DATA_DIR / filename
    if not path.exists():
        logger.warning("Seed file not found: %s", path)
        return []
    with open(path) as f:
        data = json.load(f)
    logger.info("Loaded %d records from %s", len(data), filename)
    return data


def _parse_dt(val: Any) -> datetime:
    """Parse ISO datetime string, handling optional Z suffix."""
    if isinstance(val, datetime):
        return val
    s = str(val).replace("Z", "")
    return datetime.fromisoformat(s)


async def run_seeder() -> None:
    """Async wrapper — runs sync seeder in thread pool so it can be awaited from lifespan."""
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_sync_seeder)


def _build_embedding_text(restaurant: dict, menu_item: dict) -> str:
    """Construct the text that represents a menu item for embedding."""
    name = menu_item.get("name", "")
    desc = menu_item.get("description", "")
    rest_name = restaurant.get("name", "")
    cuisine = restaurant.get("cuisine", "")
    city = restaurant.get("city", "")
    return f"{name} - {desc}. Served at {rest_name} ({cuisine} cuisine) in {city}."


def _generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Batch-embed all texts in a single OpenAI API call."""
    from openai import OpenAI
    client = OpenAI()
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
        dimensions=1536,
    )
    # response.data is ordered the same as input
    return [item.embedding for item in response.data]


def _ensure_embeddings(session) -> None:
    """Generate embeddings for any menu items that have a NULL embedding vector.

    Called even when the DB is already seeded so that items inserted before the
    embedding column existed are back-filled on the next startup.
    """
    from sqlalchemy import update as sa_update

    null_rows = session.execute(
        select(MenuItem, Restaurant)
        .join(Restaurant, MenuItem.restaurant_id == Restaurant.id)
        .where(MenuItem.embedding.is_(None))
    ).all()

    if not null_rows:
        return

    logger.info("Found %d menu items with NULL embeddings — generating...", len(null_rows))
    try:
        texts = [
            _build_embedding_text(
                {"name": r.name, "cuisine": r.cuisine, "city": r.city},
                {"name": m.name, "description": m.description},
            )
            for m, r in null_rows
        ]
        embeddings = _generate_embeddings(texts)
        for (m, _), emb in zip(null_rows, embeddings):
            session.execute(
                sa_update(MenuItem).where(MenuItem.id == m.id).values(embedding=emb)
            )
        session.flush()
        logger.info("Back-filled embeddings for %d items.", len(null_rows))
    except Exception as exc:
        logger.warning("Embedding back-fill failed — keyword fallback will be used: %s", exc)


def _upsert_default_agents(session) -> None:
    """Ensure the five built-in workflow agents exist in the DB.

    Prompts and tool lists are imported directly from the agent modules so the
    DB always reflects what the runtime actually uses — no duplicated strings.
    Existing agents are updated in-place if their prompt or tools have changed.
    """
    from agents.ordering import ORDERING_SYSTEM, ORDERING_TOOLS
    from agents.fraud import FRAUD_PROMPT, FRAUD_TOOLS
    from agents.payment import PAYMENT_PROMPT, PAYMENT_TOOLS
    from agents.notification import NOTIFICATION_PROMPT, NOTIFICATION_TOOLS
    from agents.complaint import COMPLAINT_SYSTEM, COMPLAINT_TOOLS

    defaults = [
        dict(
            name="Ordering Agent",
            role="ordering",
            system_prompt=ORDERING_SYSTEM,
            model="gpt-4o-mini",
            tools=ORDERING_TOOLS,
            channels=[],
            skills=["search", "food-ordering"],
        ),
        dict(
            name="Fraud Agent",
            role="fraud",
            system_prompt=FRAUD_PROMPT,
            model="gpt-4o-mini",
            tools=FRAUD_TOOLS,
            channels=[],
            skills=["fraud-detection", "risk-assessment"],
        ),
        dict(
            name="Payment Agent",
            role="payment",
            system_prompt=PAYMENT_PROMPT,
            model="gpt-4o-mini",
            tools=PAYMENT_TOOLS,
            channels=[],
            skills=["payment-routing", "gateway-selection"],
        ),
        dict(
            name="Notification Agent",
            role="notification",
            system_prompt=NOTIFICATION_PROMPT,
            model="gpt-4o-mini",
            tools=NOTIFICATION_TOOLS,
            channels=["telegram"],
            skills=["notifications", "telegram"],
        ),
        dict(
            name="Complaint Agent",
            role="complaint",
            system_prompt=COMPLAINT_SYSTEM,
            model="gpt-4o-mini",
            tools=COMPLAINT_TOOLS,
            channels=[],
            skills=["complaint-resolution", "customer-support"],
        ),
    ]

    existing: dict[str, Agent] = {
        a.name: a for a in session.execute(select(Agent)).scalars().all()
    }
    added = updated = 0
    for spec in defaults:
        name = spec["name"]
        if name in existing:
            agent = existing[name]
            changed = False
            for field in ("system_prompt", "tools", "model", "channels", "skills"):
                if getattr(agent, field) != spec[field]:
                    setattr(agent, field, spec[field])
                    changed = True
            if changed:
                updated += 1
        else:
            session.add(Agent(**spec))
            added += 1
    if added or updated:
        session.flush()
        logger.info("Default agents: %d added, %d updated.", added, updated)


def _upsert_workflow_templates(session) -> None:
    """Add any workflow templates that don't yet exist in the DB."""
    existing_types = {
        wf.template_type
        for wf in session.execute(select(Workflow)).scalars().all()
    }
    templates = [
        Workflow(
            name="Smart Food Ordering Concierge",
            description="End-to-end food ordering with HITL confirmation via Telegram.",
            template_type="food_ordering",
            config={
                "nodes": ["router", "ordering", "fraud", "payment", "hitl", "notification"],
                "entry": "router",
            },
        ),
Workflow(
            name="Wrong Order Resolution",
            description="Customer complaint workflow: AI agent looks up order, decides re-order or refund, routes to HITL approval.",
            template_type="complaint_resolution",
            config={
                "nodes": ["router", "complaint", "fraud", "hitl", "notification"],
                "entry": "router",
            },
        ),
    ]
    added = 0
    for wf in templates:
        if wf.template_type not in existing_types:
            session.add(wf)
            added += 1
    if added:
        session.flush()
        logger.info("Added %d new workflow template(s).", added)


def _run_sync_seeder() -> None:
    with get_sync_session() as session:
        # Check if already seeded
        existing = session.execute(select(Restaurant).limit(1)).scalars().first()
        if existing is not None:
            logger.info("Database already seeded — checking for NULL embeddings, new templates, and agents...")
            _ensure_embeddings(session)
            _upsert_workflow_templates(session)
            _upsert_default_agents(session)
            session.commit()
            return

        logger.info("Seeding database from %s ...", MOCK_DATA_DIR)

        # Load both files up-front so we can reuse them for embedding generation
        restaurants_data = _load("restaurants.json")
        menus_data = _load("menus.json")
        restaurant_lookup: dict[str, dict] = {r["id"]: r for r in restaurants_data}

        # Restaurants — flush first so menu_items FK resolves
        for r in restaurants_data:
            session.add(Restaurant(
                id=UUID(r["id"]),
                name=r["name"],
                city=r["city"],
                cuisine=r["cuisine"],
                rating=float(r["rating"]),
                address=r["address"],
                delivery_time_mins=int(r["delivery_time_mins"]),
                is_active=r.get("is_active", True),
            ))
        session.flush()
        logger.info("Restaurants inserted.")

        # Menu items — depends on restaurants; no embedding yet (nullable column)
        for m in menus_data:
            session.add(MenuItem(
                id=UUID(m["id"]),
                restaurant_id=UUID(m["restaurant_id"]),
                name=m["name"],
                description=m["description"],
                price=float(m["price"]),
                category=m["category"],
                is_available=m.get("is_available", True),
            ))
        session.flush()
        logger.info("Menu items inserted.")

        # --- Embedding generation (one batch API call for all 500 items) ---
        try:
            embedding_texts: list[str] = []
            item_ids: list[UUID] = []
            for m in menus_data:
                restaurant = restaurant_lookup.get(m["restaurant_id"], {})
                embedding_texts.append(_build_embedding_text(restaurant, m))
                item_ids.append(UUID(m["id"]))

            logger.info("Generating embeddings for %d menu items...", len(embedding_texts))
            embeddings = _generate_embeddings(embedding_texts)

            # Bulk-update each MenuItem row with its embedding vector
            from sqlalchemy import update as sa_update
            for item_id, emb in zip(item_ids, embeddings):
                session.execute(
                    sa_update(MenuItem)
                    .where(MenuItem.id == item_id)
                    .values(embedding=emb)
                )
            session.flush()
            logger.info("Embeddings stored for all menu items.")
        except Exception as exc:
            logger.warning(
                "Embedding generation failed — search will fall back to keyword matching: %s", exc
            )

        # Payment gateways
        for p in _load("payment_routes.json"):
            session.add(PaymentGateway(
                id=UUID(p["id"]),
                name=p["name"],
                method=p["method"],
                success_rate=float(p["success_rate"]),
                fee_percent=float(p["fee_percent"]),
                is_active=p.get("is_active", True),
            ))
        session.flush()
        logger.info("Payment gateways inserted.")

        # Fraud rules
        for f in _load("fraud_rules.json"):
            session.add(FraudRule(
                id=UUID(f["id"]),
                rule_name=f["rule_name"],
                rule_type=f["rule_type"],
                threshold=float(f["threshold"]),
                action=f["action"],
                description=f["description"],
            ))
        session.flush()
        logger.info("Fraud rules inserted.")

        # Users — flush before orders/transactions which FK to users
        for u in _load("users.json"):
            session.add(User(
                id=UUID(u["id"]),
                telegram_chat_id=u.get("telegram_chat_id"),
                name=u["name"],
                email=u["email"],
                city=u["city"],
                preferences=u.get("preferences", {}),
            ))
        session.flush()
        logger.info("Users inserted.")

        # Orders — depends on restaurants and users
        for o in _load("orders.json"):
            session.add(Order(
                id=UUID(o["id"]),
                user_id=UUID(o["user_id"]),
                restaurant_id=UUID(o["restaurant_id"]),
                item_name=o["item_name"],
                amount=float(o["amount"]),
                status=o["status"],
                created_at=_parse_dt(o["created_at"]),
            ))
        session.flush()
        logger.info("Orders inserted.")

        # Transactions — must come after orders and users
        for t in _load("transactions.json"):
            session.add(Transaction(
                id=UUID(t["id"]),
                user_id=UUID(t["user_id"]),
                order_id=UUID(t["order_id"]) if t.get("order_id") else None,
                amount=float(t["amount"]),
                gateway=t["gateway"],
                method=t["method"],
                status=t["status"],
                fraud_score=int(t.get("fraud_score", 0)),
                created_at=_parse_dt(t["created_at"]),
            ))
        logger.info("Transactions inserted.")

        # Workflow templates — upsert via shared helper
        _upsert_workflow_templates(session)

        # Default agent configurations
        _upsert_default_agents(session)

        logger.info("Database seeding complete.")

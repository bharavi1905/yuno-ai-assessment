TEMPLATE_CONFIG = {
    "name": "Smart Food Ordering Concierge",
    "template_type": "food_ordering",
    "description": "Multi-agent food ordering with fraud check and HITL confirmation",
    "nodes": ["router", "ordering", "fraud", "payment", "hitl", "notification"],
    "agents": [
        {"role": "ordering",     "model": "gpt-4o-mini", "tools": ["restaurant_search", "menu_retrieval"]},
        {"role": "fraud",        "model": "gpt-4o-mini", "tools": ["fraud_scoring"]},
        {"role": "payment",      "model": "gpt-4o-mini", "tools": ["payment_routing"]},
        {"role": "notification", "model": "gpt-4o-mini", "tools": ["telegram_notify"]},
    ],
}

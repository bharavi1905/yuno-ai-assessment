from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, and_, func

from core.database import get_sync_session
from models.seed_data import FraudRule, Transaction
from mcp_tools.server import mcp


@mcp.tool()
def fraud_scoring(
    amount: float,
    user_id: Optional[str] = None,
    gateway: Optional[str] = None,
    retry_count: int = 0,
) -> dict:
    """Score a transaction for fraud risk using rule-based logic.

    Returns a FraudResult dict with decision, fraud_score, triggered_rules, reasoning.
    """
    with get_sync_session() as session:
        rules = session.execute(select(FraudRule)).scalars().all()

        score = 0
        triggered: list[str] = []

        # Amount-based rules
        if amount > 10000:
            score += 35
            triggered.append("high_amount_critical")
        elif amount > 5000:
            score += 20
            triggered.append("high_amount_moderate")

        # Retry penalty
        if retry_count > 0:
            penalty = 15 * retry_count
            score += penalty
            triggered.append(f"retry_penalty_x{retry_count}")

        if retry_count > 2:
            score += 25
            triggered.append("excessive_retries")

        # User transaction history: >3 failed in last 24h
        if user_id:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            failed_count = session.execute(
                select(func.count()).select_from(Transaction).where(
                    and_(
                        Transaction.user_id == user_id,
                        Transaction.status == "failed",
                        Transaction.created_at >= cutoff,
                    )
                )
            ).scalar() or 0

            if failed_count > 3:
                score += 30
                triggered.append("multiple_recent_failures")

        # Apply any DB rules that match
        for rule in rules:
            if rule.rule_type == "amount_threshold" and amount >= rule.threshold:
                if rule.rule_name not in triggered:
                    triggered.append(rule.rule_name)

        score = min(score, 100)
        decision = "block" if score >= 70 else "approve"

        return {
            "decision": decision,
            "fraud_score": score,
            "triggered_rules": triggered,
            "reasoning": (
                f"Score {score}/100. "
                + (f"Rules triggered: {', '.join(triggered)}." if triggered else "No rules triggered.")
                + f" Decision: {decision}."
            ),
        }

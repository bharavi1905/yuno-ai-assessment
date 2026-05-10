from typing import Optional

from sqlalchemy import select

from core.database import get_sync_session
from models.seed_data import PaymentGateway
from mcp_tools.server import mcp


@mcp.tool()
def payment_routing(
    amount: float,
    preferred_method: Optional[str] = None,
    exclude_gateway: Optional[str] = None,
) -> list[dict]:
    """Select the best payment gateways for the given amount.

    Returns top 3 options sorted by success_rate desc, fee_percent asc.
    """
    with get_sync_session() as session:
        query = select(PaymentGateway).where(
            PaymentGateway.is_active == True  # noqa: E712
        )

        if preferred_method:
            query = query.where(
                PaymentGateway.method.ilike(f"%{preferred_method}%")
            )

        if exclude_gateway:
            query = query.where(
                ~PaymentGateway.name.ilike(f"%{exclude_gateway}%")
            )

        query = query.order_by(
            PaymentGateway.success_rate.desc(),
            PaymentGateway.fee_percent.asc(),
        ).limit(3)

        gateways = session.execute(query).scalars().all()

        results = []
        for gw in gateways:
            fee_amount = round(amount * gw.fee_percent / 100, 2)
            results.append({
                "gateway_name": gw.name,
                "method": gw.method,
                "success_rate": gw.success_rate,
                "fee_percent": gw.fee_percent,
                "fee_amount": fee_amount,
                "total_amount": round(amount + fee_amount, 2),
                "base_amount": amount,
            })

        return results

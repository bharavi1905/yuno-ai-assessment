from pydantic import BaseModel, ConfigDict


class PaymentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gateway_name: str
    method: str
    success_rate: float
    fee_percent: float
    fee_amount: float
    total_amount: float
    base_amount: float

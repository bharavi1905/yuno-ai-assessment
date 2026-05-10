from pydantic import BaseModel, ConfigDict


class FraudResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision: str           # "approve" | "block"
    fraud_score: int        # 0–100
    triggered_rules: list[str]
    reasoning: str

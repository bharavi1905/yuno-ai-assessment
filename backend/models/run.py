from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class WorkflowRun(SQLModel, table=True):
    __tablename__ = "workflow_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workflow_id: Optional[UUID] = Field(default=None, foreign_key="workflows.id")
    run_id: str = Field(unique=True, index=True)
    status: str = Field(default="running")  # running|hitl_pending|completed|failed|cancelled
    workflow_type: str
    triggered_by: str  # telegram | ui
    telegram_chat_id: Optional[str] = Field(default=None)

    # Token/cost tracking
    total_input_tokens: int = Field(default=0)
    total_output_tokens: int = Field(default=0)
    total_cost_usd: float = Field(default=0.0)

    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)
    error: Optional[str] = Field(default=None)

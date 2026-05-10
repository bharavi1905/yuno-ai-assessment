from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, Column
from sqlalchemy import JSON


class RunMessage(SQLModel, table=True):
    __tablename__ = "run_messages"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: str = Field(index=True)
    node_name: str
    event_type: str  # node_start | node_complete | hitl_pending | hitl_response | error
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=datetime.utcnow)

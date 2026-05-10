from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, Column
from sqlalchemy import JSON


class Agent(SQLModel, table=True):
    __tablename__ = "agents"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(unique=True, index=True)
    role: str
    system_prompt: str
    model: str = Field(default="gpt-4o-mini")
    tools: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    channels: List[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Schedule
    schedule: Optional[str] = Field(default=None)

    # Memory settings
    memory_enabled: bool = Field(default=False)
    memory_window: int = Field(default=10)

    # Skills — display/assignment metadata only
    skills: List[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Interaction rules
    interaction_rules: Optional[str] = Field(default=None)

    # Guardrails
    guardrails: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from core.database import get_session
from models.agent import Agent
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str
    role: str
    system_prompt: str
    model: str = "gpt-4o-mini"
    tools: list[str] = []
    channels: list[str] = []
    schedule: Optional[str] = None
    memory_enabled: bool = False
    memory_window: int = 10
    skills: list[str] = []
    interaction_rules: Optional[str] = None
    guardrails: Optional[dict] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    tools: Optional[list[str]] = None
    channels: Optional[list[str]] = None
    schedule: Optional[str] = None
    memory_enabled: Optional[bool] = None
    memory_window: Optional[int] = None
    skills: Optional[list[str]] = None
    interaction_rules: Optional[str] = None
    guardrails: Optional[dict] = None


class AgentResponse(BaseModel):
    id: str
    name: str
    role: str
    system_prompt: str
    model: str
    tools: list[str]
    channels: list[str]
    schedule: Optional[str]
    memory_enabled: bool
    memory_window: int
    skills: list[str]
    interaction_rules: Optional[str]
    guardrails: Optional[dict]
    created_at: datetime
    updated_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)


def _to_response(agent: Agent) -> AgentResponse:
    return AgentResponse(
        id=str(agent.id),
        name=agent.name,
        role=agent.role,
        system_prompt=agent.system_prompt,
        model=agent.model,
        tools=agent.tools or [],
        channels=agent.channels or [],
        schedule=agent.schedule,
        memory_enabled=agent.memory_enabled,
        memory_window=agent.memory_window,
        skills=agent.skills or [],
        interaction_rules=agent.interaction_rules,
        guardrails=agent.guardrails,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    body: AgentCreate,
    session: AsyncSession = Depends(get_session),
) -> AgentResponse:
    existing = (await session.execute(
        select(Agent).where(Agent.name == body.name)
    )).scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Agent name '{body.name}' already exists")

    agent = Agent(
        name=body.name,
        role=body.role,
        system_prompt=body.system_prompt,
        model=body.model,
        tools=body.tools,
        channels=body.channels,
        schedule=body.schedule,
        memory_enabled=body.memory_enabled,
        memory_window=body.memory_window,
        skills=body.skills,
        interaction_rules=body.interaction_rules,
        guardrails=body.guardrails,
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return _to_response(agent)


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    role: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[AgentResponse]:
    q = select(Agent).order_by(Agent.created_at.desc()).limit(limit).offset(offset)
    if role:
        q = q.where(Agent.role == role)
    agents = (await session.execute(q)).scalars().all()
    return [_to_response(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentResponse, responses={404: {"description": "Not found"}})
async def get_agent(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
) -> AgentResponse:
    from uuid import UUID
    try:
        uid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent = (await session.execute(
        select(Agent).where(Agent.id == uid)
    )).scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _to_response(agent)


@router.put("/{agent_id}", response_model=AgentResponse, responses={404: {"description": "Not found"}})
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    session: AsyncSession = Depends(get_session),
) -> AgentResponse:
    from uuid import UUID
    try:
        uid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent = (await session.execute(
        select(Agent).where(Agent.id == uid)
    )).scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    updates = body.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(agent, field, value)
    agent.updated_at = datetime.utcnow()

    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return _to_response(agent)


@router.delete("/{agent_id}", status_code=204, responses={404: {"description": "Not found"}})
async def delete_agent(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    from uuid import UUID
    try:
        uid = UUID(agent_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent = (await session.execute(
        select(Agent).where(Agent.id == uid)
    )).scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    await session.delete(agent)
    await session.commit()

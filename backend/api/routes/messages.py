from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from models.message import RunMessage

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class MessageCreate(BaseModel):
    run_id: str
    node_name: str
    event_type: str
    payload: dict


class MessageResponse(BaseModel):
    id: str
    run_id: str
    node_name: str
    event_type: str
    payload: dict
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)


def _to_response(msg: RunMessage) -> MessageResponse:
    return MessageResponse(
        id=str(msg.id),
        run_id=msg.run_id,
        node_name=msg.node_name,
        event_type=msg.event_type,
        payload=msg.payload or {},
        timestamp=msg.timestamp,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=MessageResponse, status_code=201)
async def create_message(
    body: MessageCreate,
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    msg = RunMessage(
        run_id=body.run_id,
        node_name=body.node_name,
        event_type=body.event_type,
        payload=body.payload,
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return _to_response(msg)


@router.get("", response_model=list[MessageResponse])
async def list_messages(
    run_id: str = Query(..., description="Filter by run_id (required)"),
    node_name: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[MessageResponse]:
    q = (
        select(RunMessage)
        .where(RunMessage.run_id == run_id)
        .order_by(RunMessage.timestamp.asc())
    )
    if node_name:
        q = q.where(RunMessage.node_name == node_name)
    if event_type:
        q = q.where(RunMessage.event_type == event_type)

    msgs = (await session.execute(q)).scalars().all()
    return [_to_response(m) for m in msgs]

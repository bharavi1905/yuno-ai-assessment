from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from models.run import WorkflowRun
from models.message import RunMessage


class HITLStateResponse(BaseModel):
    hitl_action: str
    workflow_type: str
    order_summary: Optional[dict] = None
    fraud_result: Optional[dict] = None
    payment_result: Optional[dict] = None
    resolution_result: Optional[dict] = None
    retry_count: int = 0
    hitl_expires_at: Optional[str] = None

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class RunResponse(BaseModel):
    id: str
    run_id: str
    workflow_type: str
    status: str
    triggered_by: str
    telegram_chat_id: Optional[str]
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    started_at: datetime
    completed_at: Optional[datetime]
    error: Optional[str]
    model_config = ConfigDict(from_attributes=True)


class RunMessageResponse(BaseModel):
    id: str
    run_id: str
    node_name: str
    event_type: str
    payload: dict
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)


def _run_to_response(run: WorkflowRun) -> RunResponse:
    return RunResponse(
        id=str(run.id),
        run_id=run.run_id,
        workflow_type=run.workflow_type,
        status=run.status,
        triggered_by=run.triggered_by,
        telegram_chat_id=run.telegram_chat_id,
        total_input_tokens=run.total_input_tokens,
        total_output_tokens=run.total_output_tokens,
        total_cost_usd=run.total_cost_usd,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error=run.error,
    )


def _msg_to_response(msg: RunMessage) -> RunMessageResponse:
    return RunMessageResponse(
        id=str(msg.id),
        run_id=msg.run_id,
        node_name=msg.node_name,
        event_type=msg.event_type,
        payload=msg.payload or {},
        timestamp=msg.timestamp,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[RunResponse])
async def list_runs(
    workflow_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[RunResponse]:
    q = select(WorkflowRun).order_by(WorkflowRun.started_at.desc()).limit(limit).offset(offset)
    if workflow_type:
        q = q.where(WorkflowRun.workflow_type == workflow_type)
    if status:
        q = q.where(WorkflowRun.status == status)
    runs = (await session.execute(q)).scalars().all()
    return [_run_to_response(r) for r in runs]


@router.get("/{run_id}", response_model=RunResponse, responses={404: {"description": "Not found"}})
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    run = (await session.execute(
        select(WorkflowRun).where(WorkflowRun.run_id == run_id)
    )).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_response(run)


@router.get("/{run_id}/messages", response_model=list[RunMessageResponse])
async def get_run_messages(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[RunMessageResponse]:
    msgs = (await session.execute(
        select(RunMessage)
        .where(RunMessage.run_id == run_id)
        .order_by(RunMessage.timestamp.asc())
    )).scalars().all()
    return [_msg_to_response(m) for m in msgs]


@router.get("/{run_id}/hitl", response_model=HITLStateResponse, responses={404: {"description": "Not found"}, 409: {"description": "Not in HITL state"}})
async def get_hitl_state(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> HITLStateResponse:
    run = (await session.execute(
        select(WorkflowRun).where(WorkflowRun.run_id == run_id)
    )).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "hitl_pending":
        raise HTTPException(status_code=409, detail="Run is not in hitl_pending state")

    chat_id = run.telegram_chat_id or ""
    thread_id = chat_id if chat_id else run_id
    config = {"configurable": {"thread_id": thread_id}}

    try:
        from graph.builder import get_graph
        graph = get_graph(run.workflow_type)
        state = await graph.aget_state(config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read checkpoint: {exc}")

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="No checkpoint state found")

    s = state.values
    return HITLStateResponse(
        hitl_action=s.get("hitl_action", "place_order"),
        workflow_type=s.get("workflow_type", run.workflow_type),
        order_summary=s.get("order_summary"),
        fraud_result=s.get("fraud_result"),
        payment_result=s.get("payment_result"),
        resolution_result=s.get("resolution_result"),
        retry_count=s.get("retry_count", 0),
        hitl_expires_at=s.get("hitl_expires_at"),
    )


@router.delete("/{run_id}", status_code=204, responses={404: {"description": "Not found"}})
async def archive_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    run = (await session.execute(
        select(WorkflowRun).where(WorkflowRun.run_id == run_id)
    )).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    run.status = "archived"
    session.add(run)
    await session.commit()

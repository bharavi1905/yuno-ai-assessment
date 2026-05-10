import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from models.workflow import Workflow
from models.run import WorkflowRun

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str
    template_type: str
    config: dict
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TriggerWorkflowRequest(BaseModel):
    workflow_type: str
    telegram_chat_id: str = ""
    user_message: str = ""
    amount: Optional[float] = None
    failed_gateway: Optional[str] = None
    order_id: Optional[str] = None


class TriggerWorkflowResponse(BaseModel):
    run_id: str
    workflow_type: str
    status: str
    hitl_status: str
    message: str


def _workflow_to_response(wf: Workflow) -> WorkflowResponse:
    return WorkflowResponse(
        id=str(wf.id),
        name=wf.name,
        description=wf.description,
        template_type=wf.template_type,
        config=wf.config or {},
        is_active=wf.is_active,
        created_at=wf.created_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    session: AsyncSession = Depends(get_session),
) -> list[WorkflowResponse]:
    workflows = (await session.execute(
        select(Workflow).order_by(Workflow.created_at.asc())
    )).scalars().all()
    return [_workflow_to_response(wf) for wf in workflows]


@router.get("/{workflow_id}", response_model=WorkflowResponse, responses={404: {"description": "Not found"}})
async def get_workflow(
    workflow_id: str,
    session: AsyncSession = Depends(get_session),
) -> WorkflowResponse:
    from uuid import UUID
    try:
        uid = UUID(workflow_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Workflow not found")

    wf = (await session.execute(
        select(Workflow).where(Workflow.id == uid)
    )).scalars().first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _workflow_to_response(wf)


@router.post("/trigger", response_model=TriggerWorkflowResponse)
async def trigger_workflow(
    req: TriggerWorkflowRequest,
    session: AsyncSession = Depends(get_session),
) -> TriggerWorkflowResponse:
    if req.workflow_type not in ("food_ordering", "complaint_resolution"):
        raise HTTPException(
            status_code=422,
            detail="workflow_type must be food_ordering or complaint_resolution",
        )
    # telegram_chat_id is optional for UI-triggered runs; Telegram sends a real ID

    run_id = str(uuid.uuid4())
    chat_id = req.telegram_chat_id.strip()
    # Use run_id as thread_id when no Telegram chat_id is provided (UI-triggered run).
    # Telegram-triggered runs use chat_id so the bot can resume via the same thread.
    thread_id = chat_id if chat_id else run_id

    # Look up workflow template for FK (optional — graceful if not found)
    wf_template = (await session.execute(
        select(Workflow).where(Workflow.template_type == req.workflow_type)
    )).scalars().first()

    # Persist WorkflowRun with status=running
    run = WorkflowRun(
        run_id=run_id,
        workflow_id=wf_template.id if wf_template else None,
        workflow_type=req.workflow_type,
        status="running",
        triggered_by="ui",
        telegram_chat_id=chat_id,
    )
    session.add(run)
    await session.commit()

    from graph.builder import get_graph

    if req.workflow_type == "complaint_resolution":
        initial_state = _complaint_resolution_state(run_id, chat_id, req)
    else:
        initial_state = _food_ordering_state(run_id, chat_id, req)

    config = {"configurable": {"thread_id": thread_id}}
    graph = get_graph(req.workflow_type)

    try:
        result = await graph.ainvoke(initial_state, config=config)
    except Exception as exc:
        # Update run to failed
        run.status = "failed"
        run.error = str(exc)
        run.completed_at = datetime.utcnow()
        session.add(run)
        await session.commit()
        raise HTTPException(status_code=500, detail=f"Graph invocation failed: {exc}")

    # Update WorkflowRun with final state
    hitl_status = result.get("hitl_status", "not_required")
    final_status = "hitl_pending" if hitl_status == "pending" else result.get("workflow_status", "running")
    run.status = final_status
    token_usage = result.get("token_usage") or {}
    run.total_input_tokens = sum(v.get("input", 0) for v in token_usage.values())
    run.total_output_tokens = sum(v.get("output", 0) for v in token_usage.values())
    run.total_cost_usd = sum(v.get("cost_usd", 0.0) for v in token_usage.values())
    if final_status in ("completed", "failed", "cancelled"):
        run.completed_at = datetime.utcnow()
    session.add(run)
    await session.commit()

    # If HITL fired and a real Telegram chat_id was provided, notify via Telegram
    # and save a Redis session so the bot can pick up the YES/NO reply.
    if hitl_status == "pending" and chat_id and chat_id not in ("", "0"):
        hitl_prompt = result.get("hitl_prompt", "")
        if hitl_prompt:
            try:
                import os
                import json as _json
                from telegram import Bot
                from core.redis_client import redis_client
                tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
                if tg_token:
                    bot = Bot(token=tg_token)
                    await bot.send_message(
                        chat_id=int(chat_id),
                        text=hitl_prompt,
                        parse_mode="HTML",
                    )
                await redis_client.setex(
                    f"telegram:session:{chat_id}",
                    600,
                    _json.dumps({
                        "active_run_id": run_id,
                        "hitl_status": "pending",
                        "hitl_expires_at": result.get("hitl_expires_at", ""),
                        "workflow_type": req.workflow_type,
                    }),
                )
            except Exception as tg_exc:
                import logging
                logging.getLogger(__name__).warning("Telegram HITL notify failed: %s", tg_exc)

    msg = (
        "Workflow triggered. Check Telegram for HITL confirmation prompt."
        if hitl_status == "pending"
        else "Workflow completed."
    )

    return TriggerWorkflowResponse(
        run_id=run_id,
        workflow_type=req.workflow_type,
        status=final_status,
        hitl_status=hitl_status,
        message=msg,
    )


class ResumeWorkflowRequest(BaseModel):
    approved: bool
    raw_response: str = "YES"
    reprompt: bool = False


@router.post("/{run_id}/resume", response_model=TriggerWorkflowResponse)
async def resume_workflow(
    run_id: str,
    req: ResumeWorkflowRequest,
    session: AsyncSession = Depends(get_session),
) -> TriggerWorkflowResponse:
    """Resume a workflow paused at a HITL interrupt() checkpoint."""
    from langgraph.types import Command
    from graph.builder import get_graph

    result_row = await session.execute(
        select(WorkflowRun).where(WorkflowRun.run_id == run_id)
    )
    run = result_row.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    chat_id = run.telegram_chat_id or ""
    thread_id = chat_id if chat_id else run_id
    workflow_type = run.workflow_type
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_graph(workflow_type)

    try:
        result = await graph.ainvoke(
            Command(resume={"approved": req.approved, "raw_response": req.raw_response, "reprompt": req.reprompt}),
            config=config,
        )
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        run.completed_at = datetime.utcnow()
        session.add(run)
        await session.commit()
        raise HTTPException(status_code=500, detail=f"Resume failed: {exc}")

    hitl_status = result.get("hitl_status", "not_required")
    final_status = "hitl_pending" if hitl_status == "pending" else result.get("workflow_status", "running")
    run.status = final_status
    token_usage = result.get("token_usage") or {}
    run.total_input_tokens = sum(v.get("input", 0) for v in token_usage.values())
    run.total_output_tokens = sum(v.get("output", 0) for v in token_usage.values())
    run.total_cost_usd = sum(v.get("cost_usd", 0.0) for v in token_usage.values())
    if final_status in ("completed", "failed", "cancelled"):
        run.completed_at = datetime.utcnow()
    session.add(run)
    await session.commit()

    return TriggerWorkflowResponse(
        run_id=run_id,
        workflow_type=workflow_type,
        status=final_status,
        hitl_status=hitl_status,
        message="Workflow completed." if final_status == "completed" else f"Status: {final_status}",
    )


def _food_ordering_state(run_id: str, chat_id: str, req: TriggerWorkflowRequest) -> dict:
    from tg_bot.bot import _parse_order_constraints
    return {
        "run_id": run_id,
        "workflow_type": "food_ordering",
        "telegram_chat_id": chat_id,
        "user_id": chat_id,
        "messages": [{"role": "user", "content": req.user_message}],
        "user_message": req.user_message,
        "current_step": "router",
        "workflow_status": "running",
        "execution_logs": [],
        "error": None,
        "order_constraints": _parse_order_constraints(req.user_message),
        "order_summary": None,
        "ordering_messages": [],
        "ordering_agent_thread_id": "",
        "fraud_result": None,
        "payment_result": None,

        "resolution_result": None,
        "complaint_reprompt": "",
        "hitl_status": "not_required",
        "hitl_prompt": "",
        "hitl_response": "",
        "hitl_expires_at": "",
        "hitl_action": "place_order",
        "token_usage": {},
    }



def _complaint_resolution_state(run_id: str, chat_id: str, req: TriggerWorkflowRequest) -> dict:
    return {
        "run_id": run_id,
        "workflow_type": "complaint_resolution",
        "telegram_chat_id": chat_id,
        "user_id": chat_id,
        "messages": [{"role": "user", "content": req.user_message}],
        "user_message": req.user_message,
        "current_step": "router",
        "workflow_status": "running",
        "execution_logs": [],
        "error": None,
        "order_constraints": {},
        "order_summary": None,
        "ordering_messages": [],
        "ordering_agent_thread_id": "",
        "fraud_result": None,
        "payment_result": None,

        "resolution_result": None,
        "complaint_reprompt": "",
        "hitl_status": "not_required",
        "hitl_prompt": "",
        "hitl_response": "",
        "hitl_expires_at": "",
        "hitl_action": "resolve_complaint",
        "token_usage": {},
    }

import json
import queue
import threading
import time
import uuid
from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.agents.main.profiles import get_profile, normalize_agent_type
from app.agents.main.runner import (
    _workspace_name_for_run,
    approve_agent_run,
    run_agent,
    run_to_public_dict,
)
from app.db import SessionLocal, get_db
from app.deps import get_current_user
from app.models import AgentRun, User, Workspace, WorkspaceMember
from app.rate_limit import rate_limit
from app.schemas import AgentApproveRequest, AgentRunCreate, AgentRunResponse

router = APIRouter(prefix="/agents", tags=["agents"])


def _require_member(db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
    ok = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.workspace_id == workspace_id,
        )
        .first()
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this workspace",
        )


def _as_run_response(run: AgentRun, db: Session) -> AgentRunResponse:
    ws = db.get(Workspace, run.workspace_id)
    workspace_name = ws.name if ws else None
    return AgentRunResponse.model_validate(
        run_to_public_dict(run, workspace_name=workspace_name)
    )


def _load_run(db: Session, run_id: uuid.UUID, user_id: uuid.UUID) -> AgentRun | None:
    return (
        db.query(AgentRun)
        .options(joinedload(AgentRun.steps))
        .filter(AgentRun.id == run_id, AgentRun.user_id == user_id)
        .first()
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _stream_agent_work(
    work,
    *,
    heartbeat_seconds: float = 15.0,
) -> Generator[str, None, None]:
    """
    Run agent work in a background thread with its own DB session,
    yield LangSmith-style SSE events as they occur.

    Heartbeats keep proxies and the browser idle timer from killing long
    plan/render waits; clients may ignore `type=heartbeat`.
    """
    q: queue.Queue = queue.Queue()

    def on_event(event_type: str, payload: dict) -> None:
        q.put({"type": event_type, **payload})

    def runner() -> None:
        db = SessionLocal()
        try:
            work(db, on_event)
        except Exception as e:
            q.put({"type": "error", "detail": str(e)})
        finally:
            db.close()
            q.put(None)

    threading.Thread(target=runner, daemon=True).start()
    while True:
        try:
            item = q.get(timeout=heartbeat_seconds)
        except queue.Empty:
            yield _sse({"type": "heartbeat", "ts": time.time()})
            continue
        if item is None:
            break
        yield _sse(item)


@router.post("/runs", response_model=AgentRunResponse, status_code=201)
def start_agent_run(
    body: AgentRunCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("agent")),
):
    _require_member(db, current_user.id, body.workspace_id)
    if not body.goal.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="goal is empty"
        )

    agent_type = normalize_agent_type(body.agent_type)
    profile = get_profile(agent_type)
    max_steps = (
        body.max_steps
        if body.max_steps is not None
        else profile.default_max_steps
    )

    try:
        run = run_agent(
            db,
            workspace_id=body.workspace_id,
            user_id=current_user.id,
            goal=body.goal.strip(),
            max_steps=min(max(max_steps, 1), 10),
            agent_type=agent_type,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e

    loaded = _load_run(db, run.id, current_user.id)
    if not loaded:
        raise HTTPException(status_code=500, detail="Run missing after create")
    return _as_run_response(loaded, db)


@router.post("/runs/stream")
def start_agent_run_stream(
    body: AgentRunCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("agent")),
):
    """
    LangSmith-style live trace: SSE events as the agent runs.

    Events: run_start, llm_start, llm_delta, llm_end, step, status, done, error
    """
    _require_member(db, current_user.id, body.workspace_id)
    if not body.goal.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="goal is empty"
        )

    workspace_id = body.workspace_id
    user_id = current_user.id
    goal = body.goal.strip()
    agent_type = normalize_agent_type(body.agent_type)
    profile = get_profile(agent_type)
    max_steps = (
        body.max_steps
        if body.max_steps is not None
        else profile.default_max_steps
    )
    max_steps = min(max(max_steps, 1), 10)

    def work(session: Session, on_event) -> None:
        run = run_agent(
            session,
            workspace_id=workspace_id,
            user_id=user_id,
            goal=goal,
            max_steps=max_steps,
            agent_type=agent_type,
            on_event=on_event,
        )
        # reload with steps
        loaded = (
            session.query(AgentRun)
            .options(joinedload(AgentRun.steps))
            .filter(AgentRun.id == run.id)
            .first()
        )
        on_event(
            "done",
            {
                "run": run_to_public_dict(
                    loaded or run,
                    workspace_name=_workspace_name_for_run(session, loaded or run),
                )
            },
        )

    return StreamingResponse(
        _stream_agent_work(work),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs/{run_id}/approve", response_model=AgentRunResponse)
def approve_run(
    run_id: uuid.UUID,
    body: AgentApproveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _load_run(db, run_id, current_user.id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )
    try:
        approve_agent_run(db, run, approve=body.approve)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    loaded = _load_run(db, run_id, current_user.id)
    if not loaded:
        raise HTTPException(status_code=500, detail="Run missing after approve")
    return _as_run_response(loaded, db)


@router.post("/runs/{run_id}/approve/stream")
def approve_run_stream(
    run_id: uuid.UUID,
    body: AgentApproveRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SSE stream while resume-after-approve continues the agent."""
    existing = _load_run(db, run_id, current_user.id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )

    rid = run_id
    uid = current_user.id
    approve = body.approve

    def work(session: Session, on_event) -> None:
        run = (
            session.query(AgentRun)
            .options(joinedload(AgentRun.steps))
            .filter(AgentRun.id == rid, AgentRun.user_id == uid)
            .first()
        )
        if not run:
            raise ValueError("Run not found")
        approve_agent_run(session, run, approve=approve, on_event=on_event)
        loaded = (
            session.query(AgentRun)
            .options(joinedload(AgentRun.steps))
            .filter(AgentRun.id == rid)
            .first()
        )
        on_event(
            "done",
            {
                "run": run_to_public_dict(
                    loaded or run,
                    workspace_name=_workspace_name_for_run(session, loaded or run),
                )
            },
        )

    return StreamingResponse(
        _stream_agent_work(work),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
def get_agent_run(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _load_run(db, run_id, current_user.id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )
    return _as_run_response(run, db)


@router.get("/runs", response_model=list[AgentRunResponse])
def list_agent_runs(
    workspace_id: uuid.UUID,
    agent_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_member(db, current_user.id, workspace_id)
    # Opportunistic storage hygiene for this workspace (cheap when nothing to drop).
    from app.agents.main.storage.run_storage import prune_agent_runs

    try:
        pruned = prune_agent_runs(
            db, user_id=current_user.id, workspace_id=workspace_id
        )
        if pruned.get("deleted_by_age") or pruned.get("deleted_by_cap"):
            db.commit()
    except Exception:
        db.rollback()

    q = (
        db.query(AgentRun)
        .options(joinedload(AgentRun.steps))
        .filter(
            AgentRun.workspace_id == workspace_id,
            AgentRun.user_id == current_user.id,
        )
    )
    if agent_type:
        q = q.filter(AgentRun.agent_type == normalize_agent_type(agent_type))
    runs = q.order_by(AgentRun.created_at.desc()).limit(30).all()
    return [_as_run_response(r, db) for r in runs]


@router.post("/runs/prune")
def prune_runs(
    workspace_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually prune aged / excess agent runs for the current user."""
    if workspace_id is not None:
        _require_member(db, current_user.id, workspace_id)
    from app.agents.main.storage.run_storage import prune_agent_runs

    result = prune_agent_runs(
        db, user_id=current_user.id, workspace_id=workspace_id
    )
    db.commit()
    return {"status": "ok", **result}


@router.post("/runs/{run_id}/cancel", response_model=AgentRunResponse)
def cancel_agent_run(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cancel a run that is waiting for approval (or still marked running).

    Clears pending_tool so the UI is no longer stuck on "awaiting you".
    In-flight SSE work may finish writing a final step; the status stays cancelled.
    """
    run = _load_run(db, run_id, current_user.id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )
    if run.status not in ("running", "waiting_approval"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Run is already {run.status}",
        )
    from app.agents.main.runner.events import _append_step, _next_step_index

    run.status = "cancelled"
    run.pending_tool = None
    run.error = None
    if not (run.final_answer or "").strip() or (
        run.final_answer or ""
    ).startswith("Waiting for your approval"):
        run.final_answer = "Run cancelled by user."
    step_index = _next_step_index(db, run.id)
    _append_step(
        db,
        run,
        step_index=step_index,
        type="final",
        output={"status": "cancelled", "message": "Cancelled by user"},
    )
    from app.agents.main.storage.run_storage import compact_run_if_terminal

    compact_run_if_terminal(db, run)
    db.commit()
    db.refresh(run)
    loaded = _load_run(db, run_id, current_user.id)
    if not loaded:
        raise HTTPException(status_code=500, detail="Run missing after cancel")
    return _as_run_response(loaded, db)


@router.delete("/runs/{run_id}", status_code=204)
def delete_agent_run(
    run_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _load_run(db, run_id, current_user.id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )
    db.delete(run)
    db.commit()

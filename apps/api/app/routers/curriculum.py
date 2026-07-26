"""HTTP API for workspace curriculum (topic catalog + intake)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.curriculum.compose import compose_context_block, compose_goal
from app.curriculum.discover import discover_topics
from app.curriculum.domain import domain_label, is_curriculum_workspace
from app.curriculum.intake import intake_questions, normalize_answers, validate_required
from app.curriculum.schema import active_topics, find_topic, normalize_curriculum
from app.curriculum.service import (
    get_curriculum,
    set_last_selected,
    update_topic_preferences,
    upsert_topic,
)
from app.curriculum.validate_custom import validate_custom_topic
from app.db import get_db
from app.deps import get_current_user
from app.models import User, Workspace, WorkspaceMember
from app.rate_limit import rate_limit

router = APIRouter(prefix="/workspaces", tags=["curriculum"])


def _require_member(db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID) -> Workspace:
    membership = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.workspace_id == workspace_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ws = db.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


class CurriculumTopicOut(BaseModel):
    id: str
    title: str
    summary: str = ""
    tags: list[str] = []
    source: str = "suggested"
    status: str = "active"
    preferences: dict[str, list[str]] = {}
    updated_at: str | None = None


class CurriculumOut(BaseModel):
    enabled: bool
    domain: str = ""
    source: str = ""
    fetched_at: str | None = None
    topics: list[CurriculumTopicOut] = []
    last_selected_topic_id: str | None = None


class CustomTopicRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class IntakeAnswersRequest(BaseModel):
    answers: dict[str, str | list[str]] = Field(default_factory=dict)


class TopicPatchRequest(BaseModel):
    status: str | None = None  # active | archived
    preferences: dict[str, list[str]] | None = None


def _topic_out(t: dict) -> CurriculumTopicOut:
    return CurriculumTopicOut(
        id=str(t.get("id") or ""),
        title=str(t.get("title") or ""),
        summary=str(t.get("summary") or ""),
        tags=list(t.get("tags") or []),
        source=str(t.get("source") or "suggested"),
        status=str(t.get("status") or "active"),
        preferences={
            str(k): list(v) for k, v in (t.get("preferences") or {}).items()
        },
        updated_at=t.get("updated_at"),
    )


def _curriculum_out(
    ws: Workspace,
    cur: dict,
    *,
    enabled: bool,
    include_archived: bool = False,
) -> CurriculumOut:
    if not enabled:
        topics: list = []
    elif include_archived:
        topics = [t for t in (cur.get("topics") or []) if isinstance(t, dict)]
    else:
        topics = active_topics(cur)
    return CurriculumOut(
        enabled=enabled,
        domain=str(cur.get("domain") or ""),
        source=str(cur.get("source") or ""),
        fetched_at=cur.get("fetched_at"),
        topics=[_topic_out(t) for t in topics],
        last_selected_topic_id=cur.get("last_selected_topic_id"),
    )


@router.get("/{workspace_id}/curriculum", response_model=CurriculumOut)
def get_workspace_curriculum(
    workspace_id: uuid.UUID,
    refresh: bool = False,
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get topic catalog. Auto-discovers when empty and workspace is curriculum-capable."""
    ws = _require_member(db, current_user.id, workspace_id)
    tags = ws.tags if isinstance(ws.tags, list) else None
    enabled = is_curriculum_workspace(
        name=ws.name or "",
        description=ws.description,
        tags=tags,
    )
    if not enabled:
        return CurriculumOut(enabled=False, topics=[])

    cur = get_curriculum(ws)
    if refresh or not cur.get("topics"):
        cur = discover_topics(
            ws, db=db, user_id=current_user.id, force=refresh
        )
    return _curriculum_out(
        ws, cur, enabled=True, include_archived=include_archived
    )


@router.post("/{workspace_id}/curriculum/refresh", response_model=CurriculumOut)
def refresh_curriculum(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("agent")),
):
    ws = _require_member(db, current_user.id, workspace_id)
    tags = ws.tags if isinstance(ws.tags, list) else None
    if not is_curriculum_workspace(
        name=ws.name or "", description=ws.description, tags=tags
    ):
        raise HTTPException(
            status_code=400,
            detail="This workspace is not set up for a learning topic catalog. "
            "Add a learning-focused description or tags (e.g. learning, study).",
        )
    cur = discover_topics(ws, db=db, user_id=current_user.id, force=True)
    return _curriculum_out(ws, cur, enabled=True)


@router.post(
    "/{workspace_id}/curriculum/topics",
    response_model=CurriculumTopicOut,
    status_code=status.HTTP_201_CREATED,
)
def add_custom_topic(
    workspace_id: uuid.UUID,
    body: CustomTopicRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("agent")),
):
    ws = _require_member(db, current_user.id, workspace_id)
    tags = ws.tags if isinstance(ws.tags, list) else None
    if not is_curriculum_workspace(
        name=ws.name or "", description=ws.description, tags=tags
    ):
        raise HTTPException(
            status_code=400,
            detail="Topic catalog is only available on learning workspaces.",
        )
    result = validate_custom_topic(
        title=body.title,
        workspace_name=ws.name or "",
        workspace_description=ws.description,
        workspace_tags=tags,
        db=db,
        user_id=current_user.id,
        workspace_id=ws.id,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": result.get("code") or "off_topic",
                "message": result.get("message")
                or "That topic does not fit this workspace.",
            },
        )
    topic = result["topic"]
    upsert_topic(db, ws, topic, select=True)
    return _topic_out(topic)


@router.get("/{workspace_id}/curriculum/topics/{topic_id}/intake")
def get_topic_intake(
    workspace_id: uuid.UUID,
    topic_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws = _require_member(db, current_user.id, workspace_id)
    cur = get_curriculum(ws)
    topic = find_topic(cur, topic_id)
    if not topic or topic.get("status") == "archived":
        raise HTTPException(status_code=404, detail="Topic not found")
    domain = cur.get("domain") or domain_label(
        name=ws.name or "",
        description=ws.description,
        tags=ws.tags if isinstance(ws.tags, list) else None,
    )
    form = intake_questions(topic, domain=str(domain))
    # Pre-fill from saved preferences
    form["saved_answers"] = topic.get("preferences") or {}
    return form


@router.post("/{workspace_id}/curriculum/topics/{topic_id}/intake")
def submit_topic_intake(
    workspace_id: uuid.UUID,
    topic_id: str,
    body: IntakeAnswersRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws = _require_member(db, current_user.id, workspace_id)
    cur = get_curriculum(ws)
    topic = find_topic(cur, topic_id)
    if not topic or topic.get("status") == "archived":
        raise HTTPException(status_code=404, detail="Topic not found")
    domain = str(
        cur.get("domain")
        or domain_label(
            name=ws.name or "",
            description=ws.description,
            tags=ws.tags if isinstance(ws.tags, list) else None,
        )
    )
    form = intake_questions(topic, domain=domain)
    questions = form.get("questions") or []
    answers = normalize_answers(body.answers, questions)
    missing = validate_required(answers, questions)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Please answer required questions: {', '.join(missing)}",
        )
    cur = update_topic_preferences(db, ws, topic_id, answers)
    topic = find_topic(cur, topic_id) or topic
    goal = compose_goal(topic, preferences=answers, domain=domain)
    context = compose_context_block(topic, preferences=answers, domain=domain)
    return {
        "topic": _topic_out(topic),
        "composed_goal": goal,
        "context_block": context,
    }


@router.patch(
    "/{workspace_id}/curriculum/topics/{topic_id}",
    response_model=CurriculumTopicOut,
)
def patch_topic(
    workspace_id: uuid.UUID,
    topic_id: str,
    body: TopicPatchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws = _require_member(db, current_user.id, workspace_id)
    cur = get_curriculum(ws)
    topic = find_topic(cur, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    topic = dict(topic)
    if body.status is not None:
        st = body.status.strip().lower()
        if st not in ("active", "archived"):
            raise HTTPException(status_code=400, detail="status must be active or archived")
        topic["status"] = st
    if body.preferences is not None:
        topic["preferences"] = {
            str(k): [str(x) for x in (v or []) if str(x).strip()]
            for k, v in body.preferences.items()
        }
    upsert_topic(db, ws, topic)
    return _topic_out(topic)


@router.post("/{workspace_id}/curriculum/topics/{topic_id}/select")
def select_topic(
    workspace_id: uuid.UUID,
    topic_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ws = _require_member(db, current_user.id, workspace_id)
    cur = get_curriculum(ws)
    topic = find_topic(cur, topic_id)
    if not topic or topic.get("status") == "archived":
        raise HTTPException(status_code=404, detail="Topic not found")
    set_last_selected(db, ws, topic_id)
    return {"ok": True, "topic_id": topic_id}

"""Agents-page topic catalog APIs (dedicated surface — not Learn/curriculum routes).

The Agents UI loads topics and intake only via these endpoints so it does not
call /workspaces/.../curriculum or /learn/* routes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.curriculum.compose import compose_context_block, compose_goal
from app.curriculum.discover import discover_topics
from app.curriculum.domain import domain_label, is_curriculum_workspace
from app.curriculum.intake import intake_questions, normalize_answers, validate_required
from app.curriculum.schema import active_topics, find_topic
from app.curriculum.service import (
    get_curriculum,
    update_topic_preferences,
    upsert_topic,
)
from app.curriculum.validate_custom import validate_custom_topic
from app.db import get_db
from app.deps import get_current_user
from app.models import User, Workspace, WorkspaceMember
from app.rate_limit import rate_limit

router = APIRouter(prefix="/agents", tags=["agents-topics"])


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


class AgentTopicOut(BaseModel):
    id: str
    title: str
    summary: str = ""
    tags: list[str] = []
    source: str = "suggested"
    status: str = "active"
    preferences: dict[str, list[str]] = {}
    updated_at: str | None = None


class AgentTopicCatalogOut(BaseModel):
    enabled: bool
    domain: str = ""
    source: str = ""
    fetched_at: str | None = None
    topics: list[AgentTopicOut] = []
    last_selected_topic_id: str | None = None


class AgentCustomTopicRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class AgentIntakeAnswersRequest(BaseModel):
    answers: dict[str, str | list[str]] = Field(default_factory=dict)


def _topic_out(t: dict) -> AgentTopicOut:
    return AgentTopicOut(
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


def _catalog_out(cur: dict, *, enabled: bool) -> AgentTopicCatalogOut:
    topics = active_topics(cur) if enabled else []
    return AgentTopicCatalogOut(
        enabled=enabled,
        domain=str(cur.get("domain") or ""),
        source=str(cur.get("source") or ""),
        fetched_at=cur.get("fetched_at"),
        topics=[_topic_out(t) for t in topics],
        last_selected_topic_id=cur.get("last_selected_topic_id"),
    )


@router.get(
    "/workspaces/{workspace_id}/topics",
    response_model=AgentTopicCatalogOut,
)
def agent_list_topics(
    workspace_id: uuid.UUID,
    refresh: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Agents page: list study topics for this workspace."""
    ws = _require_member(db, current_user.id, workspace_id)
    tags = ws.tags if isinstance(ws.tags, list) else None
    enabled = is_curriculum_workspace(
        name=ws.name or "",
        description=ws.description,
        tags=tags,
    )
    if not enabled:
        return AgentTopicCatalogOut(enabled=False, topics=[])

    cur = get_curriculum(ws)
    if refresh or not cur.get("topics"):
        cur = discover_topics(ws, db=db, user_id=current_user.id, force=refresh)
    return _catalog_out(cur, enabled=True)


@router.post(
    "/workspaces/{workspace_id}/topics/refresh",
    response_model=AgentTopicCatalogOut,
)
def agent_refresh_topics(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("agent")),
):
    """Agents page: force-refresh topic catalog."""
    ws = _require_member(db, current_user.id, workspace_id)
    tags = ws.tags if isinstance(ws.tags, list) else None
    if not is_curriculum_workspace(
        name=ws.name or "", description=ws.description, tags=tags
    ):
        raise HTTPException(
            status_code=400,
            detail="This workspace is not set up for a learning topic catalog.",
        )
    cur = discover_topics(ws, db=db, user_id=current_user.id, force=True)
    return _catalog_out(cur, enabled=True)


@router.post(
    "/workspaces/{workspace_id}/topics",
    response_model=AgentTopicOut,
    status_code=status.HTTP_201_CREATED,
)
def agent_add_topic(
    workspace_id: uuid.UUID,
    body: AgentCustomTopicRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("agent")),
):
    """Agents page: add a custom topic."""
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


@router.get("/workspaces/{workspace_id}/topics/{topic_id}/intake")
def agent_get_topic_intake(
    workspace_id: uuid.UUID,
    topic_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Agents page: intake form for a topic before starting a run."""
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
    form["saved_answers"] = topic.get("preferences") or {}
    return form


@router.post("/workspaces/{workspace_id}/topics/{topic_id}/intake")
def agent_submit_topic_intake(
    workspace_id: uuid.UUID,
    topic_id: str,
    body: AgentIntakeAnswersRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Agents page: submit intake and get composed agent goal."""
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

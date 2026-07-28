import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.logging_config import get_logger
from app.models import AgentRun, AgentStep, Document, UsageEvent, User, Workspace, WorkspaceMember
from app.rate_limit import rate_limit
from app.workspaces.delete import purge_workspace

logger = get_logger("sourcebook.workspaces")
from app.agents.visual_summary.workspace.context import (
    derive_workspace_context,
    format_workspace_context_for_agent,
)
from app.curriculum.service import get_curriculum
from app.schemas import (
    ChangePasswordRequest,
    UpdateProfileRequest,
    UserResponse,
    WorkspaceContextPreviewRequest,
    WorkspaceContextPreviewResponse,
    WorkspaceCreateRequest,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from app.security import hash_password, verify_password

router = APIRouter(tags=["workspaces"])


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserResponse)
def update_profile(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.email is not None:
        existing = (
            db.query(User)
            .filter(User.email == body.email.lower(), User.id != current_user.id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = body.email.lower()
    db.commit()
    db.refresh(current_user)
    return current_user


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.hashed_password = hash_password(body.new_password)
    db.commit()
    return None


class WorkspaceCurateRequest(BaseModel):
    """Workspace Curator agent: name + user-supplied source URLs only."""

    name: str = Field(min_length=1, max_length=120)
    source_urls: list[str] = Field(default_factory=list, max_length=12)


class WorkspaceSourceOut(BaseModel):
    url: str
    final_url: str | None = None
    title: str = ""
    error: Any = None
    status_code: int | None = None
    fetched_at: str | None = None
    ok: bool = False
    chars: int = 0


class WorkspaceCurateResponse(BaseModel):
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    sources: list[WorkspaceSourceOut] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    ok_source_count: int = 0
    topic_count: int = 0
    agent: str = "workspace_curator"


class WorkspaceSetupCurriculumRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = None
    # Preferred: multiple user-supplied source URLs (Workspace Curator agent).
    source_urls: list[str] | None = None
    # Back-compat single URL.
    docs_url: str | None = Field(default=None, max_length=2000)
    docs_only: bool = True


class WorkspaceCurriculumTopicOut(BaseModel):
    id: str
    title: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    parent_id: str | None = None
    kind: str = "lesson"
    has_lesson: bool = False
    source_urls: list[str] = Field(default_factory=list)


class WorkspaceCurriculumChapterOut(BaseModel):
    id: str
    title: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    has_lesson: bool = False
    intro_id: str
    source_urls: list[str] = Field(default_factory=list)
    children: list[WorkspaceCurriculumTopicOut] = Field(default_factory=list)


class WorkspaceSetupCurriculumResponse(BaseModel):
    workspace_id: str
    domain: str = ""
    source: str = ""
    docs_url: str = ""
    source_urls: list[str] = Field(default_factory=list)
    sources: list[WorkspaceSourceOut] = Field(default_factory=list)
    topics: list[WorkspaceCurriculumTopicOut] = Field(default_factory=list)
    chapters: list[WorkspaceCurriculumChapterOut] = Field(default_factory=list)


def _chapters_from_topics(
    topics: list[dict],
    *,
    lessons: dict | None = None,
) -> tuple[list[WorkspaceCurriculumTopicOut], list[WorkspaceCurriculumChapterOut]]:
    lessons = lessons or {}
    topics_out: list[WorkspaceCurriculumTopicOut] = []
    by_id: dict[str, WorkspaceCurriculumTopicOut] = {}
    for t in topics:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "")
        if not tid:
            continue
        parent_id = str(t.get("parent_id") or "").strip() or None
        row = WorkspaceCurriculumTopicOut(
            id=tid,
            title=str(t.get("title") or ""),
            summary=str(t.get("summary") or ""),
            tags=list(t.get("tags") or []),
            parent_id=parent_id,
            kind=str(t.get("kind") or ("lesson" if parent_id else "chapter")),
            has_lesson=isinstance(lessons.get(tid), dict),
            source_urls=list(t.get("source_urls") or []),
        )
        topics_out.append(row)
        by_id[tid] = row

    children_of: dict[str, list[WorkspaceCurriculumTopicOut]] = {}
    for row in topics_out:
        if row.parent_id and row.parent_id in by_id:
            children_of.setdefault(row.parent_id, []).append(row)

    chapters: list[WorkspaceCurriculumChapterOut] = []
    for root in [r for r in topics_out if not r.parent_id]:
        chapters.append(
            WorkspaceCurriculumChapterOut(
                id=root.id,
                title=root.title,
                summary=root.summary,
                tags=root.tags,
                has_lesson=root.has_lesson,
                intro_id=root.id,
                source_urls=root.source_urls,
                children=children_of.get(root.id, []),
            )
        )
    return topics_out, chapters


@router.post(
    "/workspaces/curate-from-urls",
    response_model=WorkspaceCurateResponse,
)
def workspace_curate_from_urls(
    body: WorkspaceCurateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("agent")),
):
    """
    Workspace Curator agent (pre-create preview):
    fetch ONLY the user-supplied URLs, then structure description + topic outline.
    No open-web search inventing random sources.
    """
    from app.agents.workspace_curator import curate_from_urls

    if not body.source_urls:
        raise HTTPException(
            status_code=400,
            detail="Add at least one documentation / article URL to curate from.",
        )
    result = curate_from_urls(
        name=body.name.strip(),
        urls=list(body.source_urls),
        db=db,
        user_id=current_user.id,
        workspace_id=None,
    )
    db.commit()
    return WorkspaceCurateResponse(
        description=str(result.get("description") or ""),
        tags=list(result.get("tags") or ["learning"]),
        sources=[
            WorkspaceSourceOut(**s)
            for s in (result.get("sources") or [])
            if isinstance(s, dict) and s.get("url")
        ],
        source_urls=list(result.get("source_urls") or []),
        ok_source_count=int(result.get("ok_source_count") or 0),
        topic_count=len(result.get("topics") or []),
        agent="workspace_curator",
    )


@router.post(
    "/workspaces/{workspace_id}/setup-curriculum",
    response_model=WorkspaceSetupCurriculumResponse,
)
def workspace_setup_curriculum(
    workspace_id: uuid.UUID,
    body: WorkspaceSetupCurriculumRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("agent")),
):
    """
    Persist workspace fields + run Workspace Curator on user URLs to save
    a citable hierarchical curriculum (no random open-web inventing).
    """
    from app.agents.workspace_curator import curate_from_urls
    from app.curriculum.service import get_curriculum, save_curriculum
    from app.curriculum.domain import domain_label

    membership = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.user_id == current_user.id,
            WorkspaceMember.workspace_id == workspace_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ws = db.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if body.name is not None and body.name.strip():
        ws.name = body.name.strip()[:120]
    if body.description is not None:
        ws.description = (body.description or "").strip()[:4000] or None
    if body.tags is not None:
        tags = [str(t).strip() for t in body.tags if str(t).strip()][:12]
        if "learning" not in {t.lower() for t in tags}:
            tags = ["learning", *tags][:12]
        ws.tags = tags

    urls: list[str] = []
    if body.source_urls:
        urls.extend(str(u).strip() for u in body.source_urls if str(u).strip())
    if body.docs_url and body.docs_url.strip():
        u = body.docs_url.strip()
        if u not in urls:
            urls.append(u)
    if not urls:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one source URL to build the curriculum.",
        )

    db.add(ws)
    db.commit()
    db.refresh(ws)

    result = curate_from_urls(
        name=ws.name or body.name or "Learning",
        urls=urls,
        db=db,
        user_id=current_user.id,
        workspace_id=ws.id,
    )
    topics = list(result.get("topics") or [])
    if not topics:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not extract a curriculum from the provided URLs. "
                "Check that pages are publicly readable and look like docs/TOCs."
            ),
        )

    # Prefer curator description if user left description empty.
    if not (ws.description or "").strip() and result.get("description"):
        ws.description = str(result["description"])[:4000]
        db.add(ws)

    domain = domain_label(
        name=ws.name or "",
        description=ws.description,
        tags=ws.tags if isinstance(ws.tags, list) else None,
    )
    existing = get_curriculum(ws)
    lessons = existing.get("lessons") if isinstance(existing.get("lessons"), dict) else {}
    source_urls = list(result.get("source_urls") or urls)
    sources = list(result.get("sources") or [])

    cur = {
        "version": 1,
        "domain": domain,
        "source": "workspace_curator",
        "fetched_at": result.get("fetched_at"),
        "fingerprint": f"curator:{len(source_urls)}:{ws.name}",
        "topics": topics,
        "last_selected_topic_id": existing.get("last_selected_topic_id"),
        "lessons": lessons,
        "docs_url": source_urls[0] if source_urls else "",
        "source_urls": source_urls,
        "sources": sources,
    }
    cur = save_curriculum(db, ws, cur)
    db.commit()

    topics_out, chapters = _chapters_from_topics(
        list(cur.get("topics") or topics),
        lessons=lessons if isinstance(lessons, dict) else {},
    )
    return WorkspaceSetupCurriculumResponse(
        workspace_id=str(ws.id),
        domain=str(cur.get("domain") or domain),
        source=str(cur.get("source") or "workspace_curator"),
        docs_url=str(cur.get("docs_url") or ""),
        source_urls=list(cur.get("source_urls") or source_urls),
        sources=[
            WorkspaceSourceOut(**s)
            for s in (cur.get("sources") or sources)
            if isinstance(s, dict) and s.get("url")
        ],
        topics=topics_out,
        chapters=chapters,
    )


@router.get("/workspaces", response_model=list[WorkspaceResponse])
def list_workspace(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):

    rows = (
        db.query(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .filter(WorkspaceMember.user_id == current_user.id)
        .all()
    )

    return [
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            description=ws.description,
            tags=ws.tags if isinstance(ws.tags, list) else None,
            role=role,
        )
        for ws, role in rows
    ]


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    body: WorkspaceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tags = None
    if body.tags:
        tags = [str(t).strip() for t in body.tags if t and str(t).strip()]
    workspace = Workspace(
        name=body.name,
        description=(body.description or "").strip() or None,
        tags=tags or None,
    )
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(user_id=current_user.id, workspace_id=workspace.id, role="owner"))
    db.commit()
    db.refresh(workspace)
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        tags=workspace.tags if isinstance(workspace.tags, list) else None,
        role="owner",
    )


@router.post(
    "/workspaces/{workspace_id}/context-preview",
    response_model=WorkspaceContextPreviewResponse,
)
def preview_workspace_context(
    workspace_id: uuid.UUID,
    body: WorkspaceContextPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.user_id == current_user.id,
            WorkspaceMember.workspace_id == workspace_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Workspace not found")
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    rows = (
        db.query(Document.filename, Document.status)
        .filter(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
        .limit(50)
        .all()
    )
    doc_rows = [(str(fn or ""), str(st or "")) for fn, st in rows]

    name = body.name if body.name is not None else (workspace.name or "")
    description = (
        body.description if body.description is not None else workspace.description
    )
    tags = body.tags if body.tags is not None else (
        workspace.tags if isinstance(workspace.tags, list) else None
    )

    packet = derive_workspace_context(
        name=name,
        description=description,
        tags=tags,
        document_rows=doc_rows,
    )
    d = packet.derived
    e = packet.evidence
    policy = d.tool_policy
    return WorkspaceContextPreviewResponse(
        confidence=packet.meta.confidence,
        derivation_version=packet.meta.derivation_version,
        outcome_phrase=d.outcome_phrase,
        audience_phrase=d.audience_phrase,
        success_criteria=d.success_criteria,
        tone=d.tone,
        answer_sections=d.answer_sections,
        visual_affordances=d.visual_affordances,
        external_context_ok=policy.external_context_ok,
        max_search_documents=policy.max_search_documents,
        max_web_search=policy.max_web_search,
        documents_ready=e.documents_ready,
        documents_pending=e.documents_pending,
        filename_hints=e.filename_hints,
        agent_prompt_excerpt=format_workspace_context_for_agent(packet),
    )


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
def update_workspace(
    workspace_id: uuid.UUID,
    body: WorkspaceUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.user_id == current_user.id,
            WorkspaceMember.workspace_id == workspace_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail="Only workspace owners can edit")
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if body.name is not None:
        workspace.name = body.name
    if body.description is not None:
        workspace.description = body.description.strip() or None
    if body.tags is not None:
        workspace.tags = [
            str(t).strip() for t in body.tags if t and str(t).strip()
        ] or None
    db.commit()
    db.refresh(workspace)
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        tags=workspace.tags if isinstance(workspace.tags, list) else None,
        role=membership.role,
    )


@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.user_id == current_user.id,
            WorkspaceMember.workspace_id == workspace_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail="Only workspace owners can delete")
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        purge_workspace(db, workspace_id)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "workspace_delete_failed",
            extra={"event": "workspace_delete_failed", "workspace_id": str(workspace_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete workspace. Try again or contact support.",
        ) from None
    return None


# ── Workspace activity audit (Settings → Workspace detail) ──────────────────


class WorkspaceTopicOut(BaseModel):
    id: str
    title: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    parent_id: str | None = None
    kind: str = "lesson"
    status: str = "active"
    has_lesson: bool = False


class WorkspaceActivityCallOut(BaseModel):
    """Unified call log entry (usage event or agent step)."""

    id: str
    source: str  # usage | agent_step
    call_type: str  # llm | tool | web_search | fetch_url | other
    kind: str
    model: str | None = None
    tool_name: str | None = None
    prompt: str | None = None
    completion: str | None = None
    tool_input: Any = None
    tool_output: Any = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    meta: dict[str, Any] | None = None
    run_id: str | None = None
    created_at: datetime | None = None


class WorkspaceAgentRunOut(BaseModel):
    id: str
    goal: str
    agent_type: str
    status: str
    token_usage: int | None = None
    final_answer: str | None = None
    created_at: datetime | None = None
    step_count: int = 0


class WorkspaceActivityOut(BaseModel):
    workspace_id: str
    name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    domain: str = ""
    docs_url: str = ""
    curriculum_source: str = ""
    topics: list[WorkspaceTopicOut] = Field(default_factory=list)
    calls: list[WorkspaceActivityCallOut] = Field(default_factory=list)
    agent_runs: list[WorkspaceAgentRunOut] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


def _classify_call(
    *,
    kind: str,
    tool_name: str | None,
    meta: dict | None,
) -> str:
    ct = ""
    if isinstance(meta, dict):
        ct = str(meta.get("call_type") or "").strip().lower()
    if ct in ("llm", "tool", "web_search", "fetch_url"):
        return ct
    k = (kind or "").lower()
    tn = (tool_name or "").lower()
    if "web_search" in k or tn == "web_search":
        return "web_search"
    if "fetch_url" in k or tn == "fetch_url":
        return "fetch_url"
    if tn or k in ("tool_call", "tool_result"):
        return "tool"
    if k in (
        "agent_run",
        "learn_lesson",
        "learn_suggest",
        "curriculum_discover",
        "chat",
        "visual_summary_plan",
        "visual_summary_render",
    ):
        return "llm"
    if "llm" in k or "chat" in k:
        return "llm"
    return "other"


def _prompt_from_step_input(inp: Any) -> str | None:
    if not isinstance(inp, dict):
        return None
    msgs = inp.get("messages")
    if isinstance(msgs, list) and msgs:
        parts: list[str] = []
        for m in msgs[-12:]:
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or m.get("type") or "")
            content = m.get("content")
            if content is None:
                continue
            text = content if isinstance(content, str) else str(content)
            if text.strip():
                parts.append(f"[{role}] {text.strip()[:4000]}")
        if parts:
            return "\n\n".join(parts)[:12000]
    if inp.get("prompt"):
        return str(inp.get("prompt"))[:12000]
    return None


@router.get(
    "/workspaces/{workspace_id}/activity",
    response_model=WorkspaceActivityOut,
)
def workspace_activity(
    workspace_id: uuid.UUID,
    limit: int = Query(80, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Per-workspace audit: curriculum topics + LLM/tool/web-search calls
    with prompts and outputs for Settings workspace detail.
    """
    membership = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.user_id == current_user.id,
            WorkspaceMember.workspace_id == workspace_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ws = db.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    cur = get_curriculum(ws)
    lessons = cur.get("lessons") if isinstance(cur.get("lessons"), dict) else {}
    topics_out: list[WorkspaceTopicOut] = []
    seen_topic: set[str] = set()
    for t in cur.get("topics") or []:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "")
        if not tid or tid in seen_topic:
            continue
        seen_topic.add(tid)
        topics_out.append(
            WorkspaceTopicOut(
                id=tid,
                title=str(t.get("title") or ""),
                summary=str(t.get("summary") or ""),
                tags=list(t.get("tags") or []),
                parent_id=str(t.get("parent_id") or "").strip() or None,
                kind=str(t.get("kind") or ("lesson" if t.get("parent_id") else "chapter")),
                status=str(t.get("status") or "active"),
                has_lesson=isinstance(lessons.get(tid), dict),
            )
        )

    calls: list[WorkspaceActivityCallOut] = []

    usage_rows = (
        db.query(UsageEvent)
        .filter(UsageEvent.workspace_id == workspace_id)
        .order_by(UsageEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    for row in usage_rows:
        meta = row.meta if isinstance(row.meta, dict) else {}
        tool_name = str(meta.get("tool_name") or "") or None
        calls.append(
            WorkspaceActivityCallOut(
                id=str(row.id),
                source="usage",
                call_type=_classify_call(
                    kind=str(row.kind or ""),
                    tool_name=tool_name,
                    meta=meta,
                ),
                kind=str(row.kind or ""),
                model=row.model,
                tool_name=tool_name,
                prompt=str(meta.get("prompt") or "") or None,
                completion=str(meta.get("completion") or "") or None,
                tool_input=meta.get("tool_input"),
                tool_output=meta.get("tool_output"),
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                total_tokens=row.total_tokens,
                meta=meta,
                run_id=str(meta.get("run_id") or "") or None,
                created_at=row.created_at,
            )
        )

    runs = (
        db.query(AgentRun)
        .filter(AgentRun.workspace_id == workspace_id)
        .order_by(AgentRun.created_at.desc())
        .limit(min(40, limit))
        .all()
    )
    runs_out: list[WorkspaceAgentRunOut] = []
    for run in runs:
        steps = (
            db.query(AgentStep)
            .filter(AgentStep.run_id == run.id)
            .order_by(AgentStep.step_index.asc())
            .all()
        )
        runs_out.append(
            WorkspaceAgentRunOut(
                id=str(run.id),
                goal=str(run.goal or "")[:500],
                agent_type=str(run.agent_type or "general"),
                status=str(run.status or ""),
                token_usage=run.token_usage,
                final_answer=(run.final_answer or None),
                created_at=run.created_at,
                step_count=len(steps),
            )
        )
        for step in steps:
            stype = str(step.type or "")
            tool_name = step.tool_name
            prompt = None
            completion = None
            tool_input = step.input
            tool_output = step.output
            if stype in ("thought", "final", "llm"):
                prompt = _prompt_from_step_input(step.input)
                if isinstance(step.output, str):
                    completion = step.output[:12000]
                elif isinstance(step.output, dict):
                    completion = str(
                        step.output.get("content")
                        or step.output.get("text")
                        or step.output
                    )[:12000]
                elif step.output is not None:
                    completion = str(step.output)[:12000]
                # Also surface raw message content from thought steps
                if not completion and isinstance(step.input, dict):
                    # Sometimes content is only in a sibling field
                    pass
            call_type = _classify_call(
                kind=stype,
                tool_name=tool_name,
                meta={"call_type": "tool" if tool_name else "llm"},
            )
            if tool_name == "web_search":
                call_type = "web_search"
            elif tool_name == "fetch_url":
                call_type = "fetch_url"

            calls.append(
                WorkspaceActivityCallOut(
                    id=str(step.id),
                    source="agent_step",
                    call_type=call_type,
                    kind=stype or "step",
                    model=None,
                    tool_name=tool_name,
                    prompt=prompt,
                    completion=completion,
                    tool_input=tool_input,
                    tool_output=tool_output,
                    prompt_tokens=(
                        int(step.input.get("prompt_tokens") or 0) or None
                        if isinstance(step.input, dict)
                        else None
                    ),
                    completion_tokens=(
                        int(step.input.get("completion_tokens") or 0) or None
                        if isinstance(step.input, dict)
                        else None
                    ),
                    total_tokens=(
                        int(step.input.get("total_tokens") or 0) or None
                        if isinstance(step.input, dict)
                        else None
                    ),
                    meta={"step_index": step.step_index},
                    run_id=str(run.id),
                    created_at=step.created_at,
                )
            )

    # Newest first across mixed sources
    calls.sort(
        key=lambda c: c.created_at.timestamp() if c.created_at else 0.0,
        reverse=True,
    )
    calls = calls[:limit]

    summary = {
        "topics": len(topics_out),
        "calls": len(calls),
        "llm": sum(1 for c in calls if c.call_type == "llm"),
        "tool": sum(1 for c in calls if c.call_type == "tool"),
        "web_search": sum(1 for c in calls if c.call_type == "web_search"),
        "fetch_url": sum(1 for c in calls if c.call_type == "fetch_url"),
        "agent_runs": len(runs_out),
        "total_tokens": sum(int(c.total_tokens or 0) for c in calls),
    }

    tags = ws.tags if isinstance(ws.tags, list) else []
    return WorkspaceActivityOut(
        workspace_id=str(ws.id),
        name=ws.name or "",
        description=ws.description,
        tags=[str(t) for t in tags if t],
        domain=str(cur.get("domain") or ""),
        docs_url=str(cur.get("docs_url") or ""),
        curriculum_source=str(cur.get("source") or ""),
        topics=topics_out,
        calls=calls,
        agent_runs=runs_out,
        summary=summary,
    )

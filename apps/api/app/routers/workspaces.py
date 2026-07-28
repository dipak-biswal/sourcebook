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


class WorkspaceSuggestRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceSuggestResponse(BaseModel):
    description: str = ""
    suggested_docs_url: str = ""
    tags: list[str] = Field(default_factory=list)


class WorkspaceSetupCurriculumRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = None
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


class WorkspaceCurriculumChapterOut(BaseModel):
    id: str
    title: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    has_lesson: bool = False
    intro_id: str
    children: list[WorkspaceCurriculumTopicOut] = Field(default_factory=list)


class WorkspaceSetupCurriculumResponse(BaseModel):
    workspace_id: str
    domain: str = ""
    source: str = ""
    docs_url: str = ""
    topics: list[WorkspaceCurriculumTopicOut] = Field(default_factory=list)
    chapters: list[WorkspaceCurriculumChapterOut] = Field(default_factory=list)


@router.post(
    "/workspaces/suggest-description",
    response_model=WorkspaceSuggestResponse,
)
def workspace_suggest_description(
    body: WorkspaceSuggestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("agent")),
):
    """
    Settings create-workspace modal: curate description + docs URL from name.
    Dedicated workspace API — not /learn/* or /agents/*.
    """
    from app.learn.sources import suggest_from_name

    result = suggest_from_name(
        body.name.strip(),
        db=db,
        user_id=current_user.id,
        workspace_id=None,
    )
    return WorkspaceSuggestResponse(
        description=str(result.get("description") or ""),
        suggested_docs_url=str(result.get("suggested_docs_url") or ""),
        tags=list(result.get("tags") or ["learning"]),
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
    Settings create-workspace modal: save docs source and fetch curriculum
    from documentation (docs_only by default). Not an Agents or Learn route.
    """
    from app.agents.main.tools.fetch_url import validate_fetch_url
    from app.curriculum.discover import discover_topics
    from app.curriculum.schema import active_topics
    from app.curriculum.service import get_curriculum, save_curriculum

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

    docs_url = (body.docs_url or "").strip()
    if docs_url:
        err = validate_fetch_url(docs_url)
        if err:
            raise HTTPException(status_code=400, detail=f"Invalid docs URL: {err}")

    db.add(ws)
    db.commit()
    db.refresh(ws)

    cur = get_curriculum(ws)
    cur = dict(cur)
    cur["docs_url"] = docs_url
    save_curriculum(db, ws, cur)

    cur = discover_topics(
        ws,
        db=db,
        user_id=current_user.id,
        force=True,
        docs_url=docs_url,
        docs_only=bool(body.docs_only and docs_url),
    )
    lessons = cur.get("lessons") if isinstance(cur.get("lessons"), dict) else {}
    topics_out: list[WorkspaceCurriculumTopicOut] = []
    by_id: dict[str, WorkspaceCurriculumTopicOut] = {}
    for t in active_topics(cur):
        tid = str(t.get("id") or "")
        parent_id = str(t.get("parent_id") or "").strip() or None
        row = WorkspaceCurriculumTopicOut(
            id=tid,
            title=str(t.get("title") or ""),
            summary=str(t.get("summary") or ""),
            tags=list(t.get("tags") or []),
            parent_id=parent_id,
            kind=str(t.get("kind") or ("lesson" if parent_id else "chapter")),
            has_lesson=isinstance(lessons.get(tid), dict),
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
                children=children_of.get(root.id, []),
            )
        )

    return WorkspaceSetupCurriculumResponse(
        workspace_id=str(ws.id),
        domain=str(cur.get("domain") or ""),
        source=str(cur.get("source") or ""),
        docs_url=str(cur.get("docs_url") or ""),
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

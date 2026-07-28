"""HTTP API for the Learn page (topics + textbook lessons)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.curriculum.discover import discover_topics
from app.curriculum.domain import domain_label
from app.curriculum.schema import active_topics, find_topic
from app.curriculum.service import get_curriculum, set_last_selected
from app.db import get_db
from app.deps import get_current_user
from app.learn.lessons import get_or_generate_lesson
from app.models import User, Workspace, WorkspaceMember
from app.rate_limit import rate_limit

router = APIRouter(prefix="/workspaces", tags=["learn"])


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


class LearnTopicOut(BaseModel):
    id: str
    title: str
    summary: str = ""
    tags: list[str] = []
    has_lesson: bool = False
    parent_id: str | None = None
    kind: str = "lesson"  # chapter | lesson


class LearnChapterOut(BaseModel):
    """Main topic (chapter) with nested child lessons for the Learn sidebar."""

    id: str
    title: str
    summary: str = ""
    tags: list[str] = []
    has_lesson: bool = False
    # Synthetic "Introduction" points at the chapter's own lesson id.
    intro_id: str
    children: list[LearnTopicOut] = Field(default_factory=list)


class LearnCatalogOut(BaseModel):
    workspace_id: str
    domain: str = ""
    needs_setup: bool = False
    setup_hint: str = ""
    source: str = ""
    topics: list[LearnTopicOut] = []
    chapters: list[LearnChapterOut] = []
    last_selected_topic_id: str | None = None


class LearnKeyTerm(BaseModel):
    term: str
    definition: str


class LearnOutlineItem(BaseModel):
    id: str
    heading: str


class LearnSection(BaseModel):
    id: str
    heading: str
    body_md: str
    visual_id: str | None = None


class LearnVisual(BaseModel):
    id: str
    type: str
    title: str
    body: str | None = None
    items: list[str] | None = None
    width: str = "full"


class LearnLessonOut(BaseModel):
    topic_id: str
    title: str
    summary: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    key_terms: list[LearnKeyTerm] = Field(default_factory=list)
    outline: list[LearnOutlineItem] = Field(default_factory=list)
    sections: list[LearnSection] = Field(default_factory=list)
    visuals: list[LearnVisual] = Field(default_factory=list)
    generated_at: str | None = None
    cached: bool = False
    fallback: bool = False


def _workspace_needs_setup(ws: Workspace) -> tuple[bool, str]:
    """True when name alone is not enough to infer a learning domain."""
    desc = (ws.description or "").strip()
    tags = [str(t).strip() for t in (ws.tags or []) if str(t).strip()] if isinstance(ws.tags, list) else []
    name = (ws.name or "").strip()
    if not name:
        return True, "Add a workspace name, description, and tags so we can find topics."
    if not desc and not tags:
        return (
            True,
            "Add a short description and tags (e.g. learning, system-design, ML) "
            "so Learn can fetch relevant topics for this workspace.",
        )
    domain = domain_label(name=name, description=desc, tags=tags)
    if not domain or domain.lower() in ("general", "workspace", name.lower()):
        if not desc:
            return (
                True,
                "Describe what you want to learn (e.g. “System design interview prep” "
                "or “Machine learning fundamentals”).",
            )
    return False, ""


@router.get(
    "/{workspace_id}/learn/topics",
    response_model=LearnCatalogOut,
)
def get_learn_topics(
    workspace_id: uuid.UUID,
    refresh: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("agent")),
):
    ws = _require_member(db, current_user.id, workspace_id)
    needs, hint = _workspace_needs_setup(ws)
    if needs:
        return LearnCatalogOut(
            workspace_id=str(ws.id),
            domain="",
            needs_setup=True,
            setup_hint=hint,
            topics=[],
        )

    cur = discover_topics(
        ws,
        db=db,
        user_id=current_user.id,
        force=refresh,
    )
    lessons = cur.get("lessons") if isinstance(cur.get("lessons"), dict) else {}
    topics_out: list[LearnTopicOut] = []
    by_id: dict[str, LearnTopicOut] = {}
    for t in active_topics(cur):
        tid = str(t.get("id") or "")
        parent_id = str(t.get("parent_id") or "").strip() or None
        kind = str(t.get("kind") or ("lesson" if parent_id else "chapter"))
        row = LearnTopicOut(
            id=tid,
            title=str(t.get("title") or ""),
            summary=str(t.get("summary") or ""),
            tags=list(t.get("tags") or []),
            has_lesson=isinstance(lessons.get(tid), dict),
            parent_id=parent_id,
            kind=kind,
        )
        topics_out.append(row)
        by_id[tid] = row

    # Build chapter tree: roots (no parent) → children.
    children_of: dict[str, list[LearnTopicOut]] = {}
    for row in topics_out:
        if row.parent_id and row.parent_id in by_id:
            children_of.setdefault(row.parent_id, []).append(row)

    chapters: list[LearnChapterOut] = []
    roots = [r for r in topics_out if not r.parent_id]
    # If catalog is still flat (legacy), treat each root as a chapter with no kids.
    for root in roots:
        kids = children_of.get(root.id, [])
        chapters.append(
            LearnChapterOut(
                id=root.id,
                title=root.title,
                summary=root.summary,
                tags=root.tags,
                has_lesson=root.has_lesson,
                intro_id=root.id,
                children=kids,
            )
        )

    return LearnCatalogOut(
        workspace_id=str(ws.id),
        domain=str(cur.get("domain") or ""),
        needs_setup=False,
        source=str(cur.get("source") or ""),
        topics=topics_out,
        chapters=chapters,
        last_selected_topic_id=cur.get("last_selected_topic_id"),
    )


@router.get(
    "/{workspace_id}/learn/topics/{topic_id}/lesson",
    response_model=LearnLessonOut,
)
def get_learn_lesson(
    workspace_id: uuid.UUID,
    topic_id: str,
    refresh: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("agent")),
):
    ws = _require_member(db, current_user.id, workspace_id)
    needs, _hint = _workspace_needs_setup(ws)
    if needs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complete workspace setup before opening a lesson.",
        )

    # Ensure catalog exists so custom topic ids can resolve after discover.
    cur = get_curriculum(ws)
    if not active_topics(cur):
        cur = discover_topics(ws, db=db, user_id=current_user.id, force=False)
    if not find_topic(cur, topic_id):
        raise HTTPException(status_code=404, detail="Topic not found")

    try:
        lesson = get_or_generate_lesson(
            db,
            ws,
            topic_id,
            user_id=current_user.id,
            force=refresh,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Topic not found") from None

    try:
        set_last_selected(db, ws, topic_id)
    except Exception:
        pass

    return LearnLessonOut(
        topic_id=topic_id,
        title=str(lesson.get("title") or ""),
        summary=str(lesson.get("summary") or ""),
        prerequisites=list(lesson.get("prerequisites") or []),
        key_terms=[
            LearnKeyTerm(term=k["term"], definition=k["definition"])
            for k in (lesson.get("key_terms") or [])
            if isinstance(k, dict) and k.get("term")
        ],
        outline=[
            LearnOutlineItem(id=o["id"], heading=o["heading"])
            for o in (lesson.get("outline") or [])
            if isinstance(o, dict) and o.get("id")
        ],
        sections=[
            LearnSection(
                id=s["id"],
                heading=s["heading"],
                body_md=s["body_md"],
                visual_id=s.get("visual_id"),
            )
            for s in (lesson.get("sections") or [])
            if isinstance(s, dict) and s.get("id")
        ],
        visuals=[
            LearnVisual(
                id=v["id"],
                type=v["type"],
                title=v["title"],
                body=v.get("body"),
                items=v.get("items"),
                width=str(v.get("width") or "full"),
            )
            for v in (lesson.get("visuals") or [])
            if isinstance(v, dict) and v.get("id")
        ],
        generated_at=lesson.get("generated_at"),
        cached=bool(lesson.get("cached")),
        fallback=bool(lesson.get("fallback")),
    )

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.logging_config import get_logger
from app.models import Document, User, Workspace, WorkspaceMember
from app.workspaces.delete import purge_workspace

logger = get_logger("sourcebook.workspaces")
from app.visual_summary.workspace.context import (
    derive_workspace_context,
    format_workspace_context_for_agent,
)
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

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.logging_config import get_logger
from app.models import User, Workspace, WorkspaceMember
from app.workspaces.delete import purge_workspace

logger = get_logger("sourcebook.workspaces")
from app.schemas import (
    ChangePasswordRequest,
    UpdateProfileRequest,
    UserResponse,
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

    return [WorkspaceResponse(id=ws.id, name=ws.name, role=role) for ws, role in rows]


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    body: WorkspaceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = Workspace(name=body.name)
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(user_id=current_user.id, workspace_id=workspace.id, role="owner"))
    db.commit()
    db.refresh(workspace)
    return WorkspaceResponse(id=workspace.id, name=workspace.name, role="owner")


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
        raise HTTPException(status_code=403, detail="Only workspace owners can rename")
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    workspace.name = body.name
    db.commit()
    db.refresh(workspace)
    return WorkspaceResponse(id=workspace.id, name=workspace.name, role=membership.role)


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

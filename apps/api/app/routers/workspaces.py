from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User, Workspace, WorkspaceMember
from app.schemas import UserResponse, WorkspaceResponse

router = APIRouter(tags=["workspaces"])


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


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

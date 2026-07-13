import uuid
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.chat.service import generate_suggested_questions, run_rag_chat, iter_rag_chat_sse
from app.db import get_db
from app.deps import get_current_user
from app.models import Conversation, Message, User, WorkspaceMember
from app.rate_limit import rate_limit
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ChatSuggestionsRequest,
    ChatSuggestionsResponse,
    ConversationCreate,
    ConversationResponse,
    MessageResponse,
)


router = APIRouter(tags=["chat"])


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


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_member(db, current_user.id, body.workspace_id)

    conv = Conversation(
        workspace_id=body.workspace_id,
        user_id=current_user.id,
        title=body.title,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_member(db, current_user.id, workspace_id)
    return (
        db.query(Conversation)
        .filter(
            Conversation.workspace_id == workspace_id,
            Conversation.user_id == current_user.id,
        )
        .order_by(Conversation.created_at.desc())
        .all()
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    db.query(Message).filter(Message.conversation_id == conversation_id).delete()
    db.delete(conv)
    db.commit()
    return None


@router.post("/chat/suggestions", response_model=ChatSuggestionsResponse)
def chat_suggestions(
    body: ChatSuggestionsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("chat")),
):
    _require_member(db, current_user.id, body.workspace_id)
    questions = generate_suggested_questions(
        db, workspace_id=body.workspace_id, user_id=current_user.id
    )
    return ChatSuggestionsResponse(questions=questions)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
def list_messages(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.get(Conversation, conversation_id)

    if not conv or conv.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("chat")),
):
    if not body.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is empty",
        )

    conv = db.get(Conversation, body.conversation_id)
    if not conv or conv.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    _require_member(db, current_user.id, conv.workspace_id)

    _user_msg, asst_msg, citations = run_rag_chat(
        db, conversation=conv, user_text=body.message.strip()
    )

    return ChatResponse(
        conversation_id=conv.id,
        message=asst_msg.content,
        citations=citations,
    )


@router.post("/chat/stream")
def chat_stream(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit("chat")),
):
    if not body.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Message is empty"
        )

    conv = db.get(Conversation, body.conversation_id)

    if not conv or conv.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )

    _require_member(db, current_user.id, conv.workspace_id)

    def event_gen():
        try:
            yield from iter_rag_chat_sse(
                db, conversation=conv, user_text=body.message.strip()
            )
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

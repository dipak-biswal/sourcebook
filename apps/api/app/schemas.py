from datetime import datetime
import uuid
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr

    model_config = {"from_attributes": True}


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    role: str

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    filename: str
    content_type: str | None
    status: str
    error: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationCreate(BaseModel):
    workspace_id: uuid.UUID
    title: str = "New chat"


class ConversationResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    citations: list | dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID
    message: str


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message: str
    citations: list[dict] = []


class AgentRunCreate(BaseModel):
    workspace_id: uuid.UUID
    goal: str
    max_steps: int = 5


class AgentStepResponse(BaseModel):
    id: uuid.UUID
    step_index: int
    type: str
    tool_name: str | None
    input: object | None = None
    output: object | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentRunResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
    goal: str
    status: str
    final_answer: str | None
    error: str | None
    token_usage: int | None
    pending_tool: dict | None = None
    created_at: datetime
    steps: list[AgentStepResponse] = []

    model_config = {"from_attributes": True}


class AgentApproveRequest(BaseModel):
    approve: bool = True

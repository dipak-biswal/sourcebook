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
    description: str | None = None
    tags: list[str] | None = None
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


class ChunkResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    workspace_id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int | None = None

    model_config = {"from_attributes": True}


class ChunkDetailResponse(ChunkResponse):
    """Chunk plus parent document filename for citation deep-links."""

    filename: str | None = None


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
    max_steps: int | None = None
    agent_type: str = "general"


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
    agent_type: str = "general"
    presentation_spec: dict | None = None
    status: str
    final_answer: str | None
    error: str | None
    token_usage: int | None
    pending_tool: dict | None = None
    created_at: datetime
    steps: list[AgentStepResponse] = []
    execution_trace: dict | None = None

    model_config = {"from_attributes": True}


class AgentApproveRequest(BaseModel):
    approve: bool = True
    # When pending_tool.kind == "questions": map of question_id → answer
    # (string for text fields, string or list[str] for checkbox option ids).
    answers: dict[str, str | list[str]] | None = None


class UpdateProfileRequest(BaseModel):
    email: EmailStr | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = None


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = None


class NoteCreateRequest(BaseModel):
    workspace_id: uuid.UUID
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=100_000)


class NoteUpdateRequest(BaseModel):
    title: str | None = None
    body: str | None = None


class WorkspaceContextPreviewRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = None


class WorkspaceContextPreviewResponse(BaseModel):
    confidence: str
    derivation_version: int
    outcome_phrase: str
    audience_phrase: str
    success_criteria: str
    tone: str
    answer_sections: list[str]
    visual_affordances: list[str]
    external_context_ok: bool
    max_search_documents: int
    max_web_search: int
    documents_ready: list[str]
    documents_pending: list[str]
    filename_hints: list[str]
    agent_prompt_excerpt: str


class ChatSuggestionsRequest(BaseModel):
    workspace_id: uuid.UUID


class ChatSuggestionsResponse(BaseModel):
    questions: list[str]

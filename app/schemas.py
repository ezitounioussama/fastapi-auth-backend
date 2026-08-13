"""Pydantic models: what the API accepts and what it returns.

The important detail in this file is what is *absent* from the response models.
`UserResponse` has no password field of any kind, so a password hash cannot leak
into a reply even by accident — FastAPI filters the response through the
declared model and drops anything else.
"""

from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, EmailStr, Field

from app import config


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """New account details."""

    email: EmailStr = Field(
        description="Email address, used as the login name.",
        examples=["student@example.com"],
    )
    password: str = Field(
        min_length=config.PASSWORD_MIN,
        max_length=config.PASSWORD_MAX,
        description=f"At least {config.PASSWORD_MIN} characters.",
        examples=["correct-horse-battery"],
    )


class LoginRequest(BaseModel):
    """Credentials for logging in."""

    email: EmailStr = Field(examples=["student@example.com"])
    password: str = Field(examples=["correct-horse-battery"])


class UserResponse(BaseModel):
    """A user as the API describes them. Deliberately has no password field."""

    id: int
    email: EmailStr
    created_at: datetime

    # from_attributes lets FastAPI build this straight from a SQLAlchemy row.
    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """The result of a successful login."""

    access_token: str = Field(description="JWT to send as 'Authorization: Bearer <token>'.")
    token_type: Literal["bearer"] = "bearer"
    expires_in_minutes: int = Field(description="How long the token stays valid.")
    user: UserResponse


# ---------------------------------------------------------------------------
# Conversations and messages
# ---------------------------------------------------------------------------


class ConversationCreate(BaseModel):
    """Start a new conversation."""

    title: str = Field(
        min_length=config.TITLE_MIN,
        max_length=config.TITLE_MAX,
        description="A short label for the thread.",
        examples=["Learning Python lists"],
    )


class MessageCreate(BaseModel):
    """Add a message to a conversation."""

    content: str = Field(
        min_length=config.MESSAGE_MIN,
        max_length=config.MESSAGE_MAX,
        description="What the user wants to say or ask.",
        examples=["What is a Python list?"],
    )


class MessageResponse(BaseModel):
    """One stored message."""

    id: int
    conversation_id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    """A conversation without its messages, for list views."""

    id: int
    title: str
    user_id: int
    created_at: datetime
    message_count: int = Field(description="How many messages the thread holds.")

    model_config = {"from_attributes": True}


class ConversationDetailResponse(BaseModel):
    """A conversation together with every message in it."""

    id: int
    title: str
    user_id: int
    created_at: datetime
    messages: List[MessageResponse]

    model_config = {"from_attributes": True}


class MessageExchangeResponse(BaseModel):
    """The result of posting a message: both turns that were saved.

    Returning the pair makes the persistence visible — the caller can see that
    the assistant's reply was stored as its own row, not merged into the user's.
    """

    conversation_id: int
    user_message: MessageResponse
    assistant_message: MessageResponse


# ---------------------------------------------------------------------------
# Everything else
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    database: Literal["connected", "unavailable"]
    timestamp: datetime


class QuizQuestion(BaseModel):
    number: int
    question: str
    options: List[str]
    answer_index: int = Field(ge=0, le=3)


class QuizRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=100, examples=["Python lists"])
    num_questions: int = Field(default=5, ge=1, le=10, examples=[3])


class QuizResponse(BaseModel):
    topic: str
    count: int
    questions: List[QuizQuestion]
    cached: bool = Field(description="True when served from the in-memory cache.")
    timestamp: datetime


class ValidationErrorItem(BaseModel):
    field: str
    message: str
    type: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
    errors: List[ValidationErrorItem] = Field(default_factory=list)

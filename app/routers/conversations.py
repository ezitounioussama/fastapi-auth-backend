"""Private conversations and their messages.

Every route here requires a valid token. Two different guards are in play:

  * `get_current_user` — is this request authenticated at all?
  * `get_owned_conversation` — does this conversation belong to the caller?

Routes that take a conversation_id use the second one, so the ownership check
cannot be forgotten in a new endpoint.
"""

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, get_owned_conversation
from app.models_db import Conversation, Message, User
from app.schemas import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
    ErrorResponse,
    MessageCreate,
    MessageExchangeResponse,
    MessageResponse,
)
from app.services import generate_assistant_reply

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
    # Applied to every route below, so the whole group is closed to anonymous
    # callers and Swagger shows each one as requiring authentication.
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse, "description": "Not authenticated"}},
)


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a conversation",
)
def create_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationResponse:
    """Create a thread owned by the caller.

    user_id comes from the token, never from the request body. If the client
    could supply it, anyone could create rows in someone else's account.
    """
    conversation = Conversation(title=payload.title, user_id=current_user.id)

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        user_id=conversation.user_id,
        created_at=conversation.created_at,
        message_count=0,
    )


@router.get(
    "",
    response_model=List[ConversationResponse],
    summary="List my conversations",
)
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ConversationResponse]:
    """Return only the caller's conversations.

    The filter on user_id is what makes the list private. Without it this would
    hand every user the whole table.
    """
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.id.desc())
        .all()
    )

    return [
        ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            user_id=conversation.user_id,
            created_at=conversation.created_at,
            message_count=len(conversation.messages),
        )
        for conversation in conversations
    ]


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetailResponse,
    responses={404: {"model": ErrorResponse, "description": "Not found, or not yours"}},
    summary="Read one conversation with its messages",
)
def get_conversation(
    conversation: Conversation = Depends(get_owned_conversation),
) -> Conversation:
    """Return a conversation and its full message history.

    The dependency has already checked ownership, so by the time this runs the
    row is guaranteed to belong to the caller.
    """
    return conversation


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageExchangeResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse, "description": "Not found, or not yours"}},
    summary="Add a message and get a reply",
    description=(
        "Saves the user's message, generates the assistant's reply, saves that "
        "too, and returns both rows."
    ),
)
def add_message(
    payload: MessageCreate,
    conversation: Conversation = Depends(get_owned_conversation),
    db: Session = Depends(get_db),
) -> MessageExchangeResponse:
    """Store the user's turn and the assistant's turn as two separate rows."""
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=payload.content,
    )
    db.add(user_message)

    reply_text = generate_assistant_reply(payload.content)

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=reply_text,
    )
    db.add(assistant_message)

    # One commit for both rows, so a failure cannot leave a question stored
    # without its answer.
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)

    return MessageExchangeResponse(
        conversation_id=conversation.id,
        user_message=MessageResponse.model_validate(user_message),
        assistant_message=MessageResponse.model_validate(assistant_message),
    )


@router.get(
    "/{conversation_id}/messages",
    response_model=List[MessageResponse],
    responses={404: {"model": ErrorResponse, "description": "Not found, or not yours"}},
    summary="List the messages in a conversation",
)
def list_messages(
    conversation: Conversation = Depends(get_owned_conversation),
) -> List[Message]:
    return conversation.messages


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse, "description": "Not found, or not yours"}},
    summary="Delete a conversation",
)
def delete_conversation(
    conversation: Conversation = Depends(get_owned_conversation),
    db: Session = Depends(get_db),
) -> None:
    """Delete a conversation and, through the cascade, all of its messages.

    Modification is guarded by the same dependency as reading, so User B cannot
    delete User A's thread either.
    """
    db.delete(conversation)
    db.commit()

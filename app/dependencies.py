"""Reusable dependencies: who is calling, and may they touch this row.

`get_current_user` turns a bearer token into a User row, and
`get_owned_conversation` fetches a conversation only if the caller owns it.
Every protected route depends on one of these, so the security rules live in one
place instead of being re-implemented per endpoint.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models_db import Conversation, User
from app.security import decode_access_token

# auto_error=False so a missing header reaches our own code, which can then
# raise a 401 carrying the WWW-Authenticate header. With auto_error=True the
# response would be a 403, which is the wrong code for "you did not
# authenticate at all".
bearer_scheme = HTTPBearer(auto_error=False, description="Paste the JWT from /auth/login.")


def _unauthorised(detail: str) -> HTTPException:
    """401 with the header the HTTP spec asks for on a failed bearer auth."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Identify the caller from the Authorization header.

    Four things can go wrong, and all of them produce the same 401 with a
    deliberately vague message. Saying "no such user" or "expired token" would
    tell an attacker which part of their guess was right.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorised("Not authenticated. Send 'Authorization: Bearer <token>'.")

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise _unauthorised("Invalid or expired token.")

    subject = payload.get("sub")
    if subject is None:
        raise _unauthorised("Invalid or expired token.")

    # `sub` is stored as a string per the JWT spec, so it has to be converted
    # back before it can be used as a primary key.
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise _unauthorised("Invalid or expired token.")

    user = db.get(User, user_id)

    # A token can be perfectly valid and still point at a deleted account.
    if user is None:
        raise _unauthorised("Invalid or expired token.")

    return user


def get_owned_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    """Load a conversation, but only if the caller owns it.

    This is the ownership rule, in one place. Any route that takes a
    conversation_id depends on this instead of querying directly, so no endpoint
    can forget the check.

    The response is 404, not 403, and that is deliberate. A 403 would confirm
    that conversation 7 exists and belongs to somebody else, which lets an
    attacker map out other people's data by trying ids. A 404 makes "not yours"
    and "does not exist" indistinguishable from outside.
    """
    conversation = db.get(Conversation, conversation_id)

    if conversation is None or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    return conversation

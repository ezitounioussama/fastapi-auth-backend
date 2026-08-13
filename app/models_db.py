"""SQLAlchemy tables: users, conversations, messages.

Shape of the data:

    users 1 ──< conversations 1 ──< messages

One user owns many conversations; one conversation holds many messages. Every
conversation carries the id of the user who created it, and that column is what
every ownership check is based on.
"""

from datetime import datetime, timezone
from typing import List

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    """Timezone-aware UTC timestamp.

    Aware rather than naive (datetime.utcnow() is both naive and deprecated),
    so stored times are unambiguous.
    """
    return datetime.now(timezone.utc)


class User(Base):
    """A registered account.

    There is no `password` column anywhere in this file. Only the bcrypt hash is
    stored, so even with a full copy of the database the original passwords
    cannot be read back.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # unique=True makes the database itself reject a duplicate email, so two
    # simultaneous registrations cannot both slip through a Python-level check.
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    # cascade="all, delete-orphan": deleting a user removes their conversations
    # rather than leaving rows pointing at an account that no longer exists.
    conversations: Mapped[List["Conversation"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User id={self.id} email={self.email!r}>"


class Conversation(Base):
    """A private thread belonging to exactly one user."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)

    # The ownership link. Indexed because every request filters on it, and
    # ondelete="CASCADE" keeps the rule at the database level too.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="conversations")

    messages: Mapped[List["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",  # oldest first, so a thread reads in order
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Conversation id={self.id} user_id={self.user_id} title={self.title!r}>"


class Message(Base):
    """One turn in a conversation, from either the user or the assistant."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # "user" or "assistant". Stored as text rather than an enum to keep the
    # SQLite schema simple; the Pydantic layer restricts the accepted values.
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    # Text rather than String(n): an assistant reply has no useful length limit.
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Message id={self.id} role={self.role!r}>"

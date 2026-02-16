"""
Ask Otto Conversation ORM model.

Tracks conversational AI conversations with Ask Otto.
"""
from sqlalchemy import String, Text, ForeignKey, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class AskOttoConversationORM(Base):
    """Ask Otto conversation ORM model."""
    
    __tablename__ = "ask_otto_conversations"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    shunya_conversation_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True, index=True)
    
    # Conversation metadata
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.current_timestamp(),
    )
    
    # Relationships
    messages = relationship("AskOttoMessageORM", back_populates="conversation", cascade="all, delete-orphan")
    company = relationship("CompanyORM")
    user = relationship("UserORM")


class AskOttoMessageORM(Base):
    """Ask Otto message ORM model."""
    
    __tablename__ = "ask_otto_messages"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("ask_otto_conversations.id"), nullable=False, index=True)
    shunya_message_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True, index=True)
    
    # Message content
    role: Mapped[str] = mapped_column(String, nullable=False)  # user, assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Message metadata (renamed from 'metadata' as it's reserved in SQLAlchemy)
    message_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    
    # Relationships
    conversation = relationship("AskOttoConversationORM", back_populates="messages")

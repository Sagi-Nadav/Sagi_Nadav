import os
from datetime import datetime, date
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Date, Boolean, ForeignKey
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/assistant.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="open")  # open|in_progress|done|deferred
    priority = Column(Integer, nullable=False, default=2)     # 1=high 2=medium 3=low
    week_of = Column(Date, nullable=False)                    # always a Monday
    due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    ms_task_id = Column(String, nullable=True)


class StyleProfile(Base):
    __tablename__ = "style_profiles"

    id = Column(Integer, primary_key=True, index=True)
    sample_text = Column(Text, nullable=False, default="")
    style_summary = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class EmailDraft(Base):
    __tablename__ = "email_drafts"

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String, nullable=True)
    to_recipients = Column(Text, nullable=False, default="[]")  # JSON list
    body_html = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default="draft")    # draft|sent|discarded
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ms_message_id = Column(String, nullable=True)


class SessionStore(Base):
    __tablename__ = "session_store"

    session_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    access_token = Column(Text, nullable=False)    # Fernet-encrypted
    refresh_token = Column(Text, nullable=False)   # Fernet-encrypted
    token_expiry = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=False, default=datetime.utcnow)


class EmailProject(Base):
    __tablename__ = "email_projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    keywords = Column(Text, nullable=False, default="[]")  # JSON list of strings
    folder_id = Column(String, nullable=True)              # MS Graph folder ID
    color = Column(String, nullable=False, default="#667eea")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ProcessedEmail(Base):
    __tablename__ = "processed_emails"

    id = Column(Integer, primary_key=True, index=True)
    ms_message_id = Column(String, nullable=False, unique=True, index=True)
    subject = Column(String, nullable=False, default="")
    from_email = Column(String, nullable=False, default="")
    from_name = Column(String, nullable=False, default="")
    received_at = Column(DateTime, nullable=True)
    project_id = Column(Integer, ForeignKey("email_projects.id"), nullable=True)
    draft_reply_html = Column(Text, nullable=True)
    approval_token = Column(String, nullable=True, unique=True, index=True)
    # status: pending | approved | rejected | sent | no_reply_needed
    status = Column(String, nullable=False, default="pending")
    notification_sent = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

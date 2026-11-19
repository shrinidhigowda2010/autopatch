"""Tables for users, projects, scans, bugs, patches, test runs and decisions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    coder_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="student")  # student | developer | admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    projects: Mapped[list[Project]] = relationship(back_populates="owner")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(20))
    sample_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    languages_json: Mapped[str] = mapped_column(Text, default="[]")
    dependencies_json: Mapped[str] = mapped_column(Text, default="[]")
    important_json: Mapped[str] = mapped_column(Text, default="[]")
    graph_json: Mapped[str] = mapped_column(Text, default="{}")
    tree_json: Mapped[str] = mapped_column(Text, default="[]")
    file_count: Mapped[int] = mapped_column(Integer, default=0)

    owner: Mapped[User | None] = relationship(back_populates="projects")
    scans: Mapped[list[Scan]] = relationship(back_populates="project")


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    mode: Mapped[str] = mapped_column(String(20), default="live")
    error: Mapped[str] = mapped_column(Text, default="")
    tool_notes_json: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="scans")
    bugs: Mapped[list[Bug]] = relationship(back_populates="scan")


class Bug(Base):
    __tablename__ = "bugs"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str] = mapped_column(String(80), default="")
    symbol: Mapped[str] = mapped_column(String(120), default="")
    file: Mapped[str] = mapped_column(String(300))
    line: Mapped[int] = mapped_column(Integer, default=1)
    end_line: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(40), default="logic")
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    impact: Mapped[str] = mapped_column(Text, default="")
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    root_cause: Mapped[str] = mapped_column(Text, default="")
    trigger: Mapped[str] = mapped_column(Text, default="")
    student_explanation: Mapped[str] = mapped_column(Text, default="")
    explanation_kn: Mapped[str] = mapped_column(Text, default="")
    explanation_hi: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(80), default="ast")
    snippet: Mapped[str] = mapped_column(Text, default="")
    extra_json: Mapped[str] = mapped_column(Text, default="{}")
    demo_cache_used: Mapped[bool] = mapped_column(Boolean, default=False)

    scan: Mapped[Scan] = relationship(back_populates="bugs")
    patches: Mapped[list[Patch]] = relationship(back_populates="bug")


class Patch(Base):
    __tablename__ = "patches"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    bug_id: Mapped[str] = mapped_column(ForeignKey("bugs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    file: Mapped[str] = mapped_column(String(300))
    diff: Mapped[str] = mapped_column(Text, default="")
    before_code: Mapped[str] = mapped_column(Text, default="")
    after_code: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed|applied|rejected|skipped
    source: Mapped[str] = mapped_column(String(40), default="rule")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    bug: Mapped[Bug] = relationship(back_populates="patches")


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    scan_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    safe_to_apply: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TestEvent(Base):
    __tablename__ = "test_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="info")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    patch_id: Mapped[str] = mapped_column(ForeignKey("patches.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40))
    # approved | rejected | edited | skipped | auto-applied | rolled_back
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkspaceVersion(Base):
    """Version timeline: v0 = original upload, v1+ after each approved fix."""

    __tablename__ = "workspace_versions"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(200), default="")
    patch_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    path: Mapped[str] = mapped_column(String(400), default="")  # relative to project root
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HistoryEvent(Base):
    __tablename__ = "history_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    bug_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Conversation(Base):
    """FixPilot Assistant chat thread, scoped to a project and optional user."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    language: Mapped[str] = mapped_column(String(8), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    messages: Mapped[list[ChatMessage]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text, default="")
    tool_steps_json: Mapped[str] = mapped_column(Text, default="[]")
    patches_json: Mapped[str] = mapped_column(Text, default="[]")
    feedback: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 helpful, -1 not helpful
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

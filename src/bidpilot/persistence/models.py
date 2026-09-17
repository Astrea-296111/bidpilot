from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Tender(Base):
    __tablename__ = "tenders"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_name: Mapped[str] = mapped_column(String(300))
    industry: Mapped[str] = mapped_column(String(100), default="unknown")
    source_file: Mapped[str] = mapped_column(Text)
    deadline: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="uploaded")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RequirementRow(Base):
    __tablename__ = "requirements"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    tender_id: Mapped[str] = mapped_column(ForeignKey("tenders.id"), index=True)
    local_id: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30))
    mandatory: Mapped[bool] = mapped_column(Boolean)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_section: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_quote: Mapped[str] = mapped_column(Text, default="")


class MatchRow(Base):
    __tablename__ = "capability_matches"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    missing_items: Mapped[list] = mapped_column(JSON)


class EvidenceRow(Base):
    __tablename__ = "evidences"
    id: Mapped[str] = mapped_column(String(150), primary_key=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("capability_matches.id"), index=True)
    document_id: Mapped[str] = mapped_column(Text)
    chunk_id: Mapped[str] = mapped_column(String(80))
    score: Mapped[float] = mapped_column(Float)
    snapshot: Mapped[dict] = mapped_column(JSON)


class BidResult(Base):
    __tablename__ = "bid_results"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tender_id: Mapped[str] = mapped_column(ForeignKey("tenders.id"), unique=True)
    score: Mapped[float] = mapped_column(Float)
    recommendation: Mapped[str] = mapped_column(String(40))
    summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tender_id: Mapped[str] = mapped_column(ForeignKey("tenders.id"), index=True)
    status: Mapped[str] = mapped_column(String(40))
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    retrieval_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Opportunity(Base):
    __tablename__ = "opportunities"
    tender_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_name: Mapped[str] = mapped_column(String(300))
    deadline: Mapped[str | None] = mapped_column(String(50), nullable=True)
    score: Mapped[float] = mapped_column(Float)
    recommendation: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ChatMemory(Base):
    __tablename__ = "chat_memory"
    thread_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    tender_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    messages: Mapped[list] = mapped_column(JSON, default=list)

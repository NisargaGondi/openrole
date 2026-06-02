"""Core persistence models for jobs, companies, contacts, and outreach."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid4())


class JobStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    REVIEWING = "reviewing"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class OutreachStatus(str, enum.Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    SENT = "sent"
    REPLIED = "replied"
    NO_RESPONSE = "no_response"


class OutreachChannel(str, enum.Enum):
    EMAIL = "email"
    LINKEDIN = "linkedin"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), index=True)
    apollo_organization_id: Mapped[str | None] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(255))
    employee_count: Mapped[int | None] = mapped_column()
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    jobs: Mapped[list[Job]] = relationship(back_populates="company")
    contacts: Mapped[list[Contact]] = relationship(back_populates="company")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    department: Mapped[str | None] = mapped_column(String(255))
    locations: Mapped[list[str] | None] = mapped_column(JSON)
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    source_platform: Mapped[str | None] = mapped_column(String(64))
    apply_url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.DISCOVERED, index=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped[Company | None] = relationship(back_populates="jobs")
    outreach: Mapped[list[Outreach]] = relationship(back_populates="job")
    applications: Mapped[list[Application]] = relationship(back_populates="job")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(2048))
    location: Mapped[str | None] = mapped_column(String(255))
    priority_rank: Mapped[int | None] = mapped_column()
    priority_reason: Mapped[str | None] = mapped_column(Text)
    research_brief: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped[Company] = relationship(back_populates="contacts")
    outreach: Mapped[list[Outreach]] = relationship(back_populates="contact")


class Outreach(Base):
    __tablename__ = "outreach"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), nullable=False, index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    channel: Mapped[OutreachChannel] = mapped_column(Enum(OutreachChannel), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[OutreachStatus] = mapped_column(
        Enum(OutreachStatus), default=OutreachStatus.DRAFT, index=True
    )
    validation_notes: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    contact: Mapped[Contact] = relationship(back_populates="outreach")
    job: Mapped[Job | None] = relationship(back_populates="outreach")


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1024))
    content_text: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    resume_id: Mapped[str | None] = mapped_column(ForeignKey("resumes.id"))
    answers_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped[Job] = relationship(back_populates="applications")

"""Models for investigation subjects and shared subject evidence."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SubjectType(str, Enum):
    PERSON = "person"
    COMPANY = "company"
    ORGANIZATION = "organization"
    DOMAIN = "domain"
    ACCOUNT = "account"
    LOCATION = "location"
    EVENT = "event"
    OTHER = "other"


class EvidenceStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class SubjectStatus(str, Enum):
    ACTIVE = "active"
    DONE = "done"


class Subject(BaseModel):
    subject_id: str
    name: str
    subject_type: SubjectType
    canonical_identifier: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    identifiers: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    investigation_goals: Optional[str] = None
    status: SubjectStatus = SubjectStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    thread_ids: list[str] = Field(default_factory=list)


class SubjectCreateRequest(BaseModel):
    name: str
    subject_type: SubjectType
    canonical_identifier: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    identifiers: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    investigation_goals: Optional[str] = None
    status: SubjectStatus = SubjectStatus.ACTIVE


class SubjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    subject_type: Optional[SubjectType] = None
    canonical_identifier: Optional[str] = None
    aliases: Optional[list[str]] = None
    identifiers: Optional[list[str]] = None
    description: Optional[str] = None
    investigation_goals: Optional[str] = None
    status: Optional[SubjectStatus] = None


class EvidenceUpdateRequest(BaseModel):
    status: Optional[EvidenceStatus] = None
    claim: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)

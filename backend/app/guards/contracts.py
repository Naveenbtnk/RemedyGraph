"""Typed contracts for generated guard previews, approvals, and executions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Self

from pydantic import Field, field_validator, model_validator

from backend.app.models import DomainModel, utc_now


class GuardType(StrEnum):
    STATIC_REPOSITORY = "static_repository"
    TEST_PROTECTION = "test_protection"
    CONFIGURATION = "configuration"


class GuardStatus(StrEnum):
    PREVIEWED = "PREVIEWED"
    REJECTED = "REJECTED"
    WRITTEN = "WRITTEN"
    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    ERROR = "ERROR"


class GuardExecutionStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    ERROR = "ERROR"


class GuardSpec(DomainModel):
    id: str
    run_id: str
    action_id: str
    invariant_id: str
    name: str
    guard_type: GuardType
    intent: str
    assumptions: list[str] = Field(default_factory=list)
    assertions: list[str] = Field(default_factory=list)
    target_path: str
    preview: str
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    template_version: str = Field(default="guard-v1", pattern=r"^guard-v\d+$")
    terms: list[str] = Field(min_length=1, max_length=6)
    test_only: bool = False
    match_all: bool = True
    expected_literals: list[str] = Field(default_factory=list, max_length=3)
    execution_label: str = "Python isolated guard"
    status: GuardStatus = GuardStatus.PREVIEWED
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("target_path")
    @classmethod
    def target_is_safe_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        candidate = PurePosixPath(normalized)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("guard target_path must be relative and traversal-free")
        if candidate.suffix != ".py" or candidate.parts[:2] != (".remedygraph", "generated_guards"):
            raise ValueError("guard target_path must be inside .remedygraph/generated_guards")
        return candidate.as_posix()

    @field_validator("terms")
    @classmethod
    def terms_are_bounded_identifiers(cls, value: list[str]) -> list[str]:
        if any(
            not term or len(term) > 64 or not all(char.isalnum() or char in "_.-" for char in term)
            for term in value
        ):
            raise ValueError("guard terms must be bounded identifiers")
        return value

    @field_validator("expected_literals")
    @classmethod
    def expected_literals_are_bounded(cls, value: list[str]) -> list[str]:
        if any(not item or len(item) > 32 for item in value):
            raise ValueError("expected literals must be non-empty and bounded")
        return value


class GuardApproval(DomainModel):
    id: str
    guard_id: str
    run_id: str
    approved: bool
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    decided_at: datetime = Field(default_factory=utc_now)


class GuardExecution(DomainModel):
    id: str
    guard_id: str
    run_id: str
    status: GuardExecutionStatus
    command_label: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = Field(default=0, ge=0)
    timed_out: bool = False
    output_truncated: bool = False
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def execution_state_is_consistent(self) -> Self:
        if self.status == GuardExecutionStatus.TIMED_OUT and not self.timed_out:
            raise ValueError("timed-out execution must set timed_out")
        if self.status == GuardExecutionStatus.PASSED and self.exit_code != 0:
            raise ValueError("passed execution requires exit_code=0")
        return self

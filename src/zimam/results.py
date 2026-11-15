from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EffectClass(StrEnum):
    READ = "READ"
    REVERSIBLE_WRITE = "REVERSIBLE_WRITE"
    RISKY_WRITE = "RISKY_WRITE"
    IRREVERSIBLE_WRITE = "IRREVERSIBLE_WRITE"


class BusinessCode(StrEnum):
    MEMBER_NOT_FOUND = "MEMBER_NOT_FOUND"
    SAVINGS_ACCOUNT_NOT_FOUND = "SAVINGS_ACCOUNT_NOT_FOUND"
    VALIDATION_REJECTED = "VALIDATION_REJECTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"


class HumanCode(StrEnum):
    TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
    UNKNOWN_DIALOG = "UNKNOWN_DIALOG"
    RISKY_ACTION_REQUIRES_APPROVAL = "RISKY_ACTION_REQUIRES_APPROVAL"
    REPEATED_RECOVERABLE_FAILURE = "REPEATED_RECOVERABLE_FAILURE"
    DISCOVERY_STUCK = "DISCOVERY_STUCK"


class FailureCode(StrEnum):
    ARTIFACT_INVALID = "ARTIFACT_INVALID"
    UNSUPPORTED_ARTIFACT_VERSION = "UNSUPPORTED_ARTIFACT_VERSION"
    TARGET_NOT_RESOLVED = "TARGET_NOT_RESOLVED"
    POSTCONDITION_FAILED = "POSTCONDITION_FAILED"
    SESSION_LOST = "SESSION_LOST"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    UNEXPECTED_APPLICATION_STATE = "UNEXPECTED_APPLICATION_STATE"
    INCOMPATIBLE_CAPABILITY = "INCOMPATIBLE_CAPABILITY"


class RecoverableCode(StrEnum):
    KNOWN_INTERSTITIAL = "KNOWN_INTERSTITIAL"
    TRANSIENT_LOAD_TIMEOUT = "TRANSIENT_LOAD_TIMEOUT"
    RETRYABLE_BACKEND_FAILURE = "RETRYABLE_BACKEND_FAILURE"


class FailureContext(BaseModel):
    run_id: str
    capability_id: str | None = None
    capability_version: str | None = None
    step_id: str | None = None
    code: str
    message: str
    expected: str | None = None
    observed: str | None = None
    last_checkpoint: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class SuccessResult(BaseModel):
    kind: Literal["success"] = "success"
    run_id: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    model_calls: int = 0
    duration_ms: int = 0
    evidence_dir: str | None = None


class BusinessOutcomeResult(BaseModel):
    kind: Literal["business_outcome"] = "business_outcome"
    run_id: str
    code: BusinessCode
    message: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    model_calls: int = 0
    duration_ms: int = 0
    evidence_dir: str | None = None


class HumanRequiredResult(BaseModel):
    kind: Literal["human_required"] = "human_required"
    run_id: str
    code: HumanCode
    message: str
    expected: str | None = None
    observed: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    outputs: dict[str, Any] = Field(default_factory=dict)
    model_calls: int = 0
    duration_ms: int = 0
    evidence_dir: str | None = None


class FailureResult(BaseModel):
    kind: Literal["failure"] = "failure"
    run_id: str
    code: FailureCode
    context: FailureContext
    outputs: dict[str, Any] = Field(default_factory=dict)
    model_calls: int = 0
    duration_ms: int = 0
    evidence_dir: str | None = None


RunResult = SuccessResult | BusinessOutcomeResult | HumanRequiredResult | FailureResult

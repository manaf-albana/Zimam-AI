from __future__ import annotations

from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, Field, TypeAdapter

from zimam.results import BusinessCode, EffectClass

SCHEMA_VERSION = "1.0"
SUPPORTED_SCHEMA_VERSIONS = {"1.0"}


class TargetDescriptor(BaseModel):
    role: str | None = None
    accessible_name: str | None = None
    label: str | None = None
    text: str | None = None
    control_type: str | None = None
    frame: str | None = None
    stable_attributes: dict[str, str] = Field(default_factory=dict)
    nearby_anchor: str | None = None
    structural_relation: str | None = None
    selector_fallback: str | None = None
    visual_hint: str | None = None


class Predicate(BaseModel):
    kind: Literal[
        "route_matches",
        "text_present",
        "element_present",
        "dialog_present",
        "field_value_matches",
        "title_matches",
    ]
    pattern: str | None = None
    text: str | None = None
    target: TargetDescriptor | None = None
    value: str | None = None


class Checkpoint(BaseModel):
    mode: Literal["all", "any"] = "all"
    predicates: list[Predicate] = Field(default_factory=list)
    timeout_ms: int = 8000


class InputSpec(BaseModel):
    name: str
    type: str = "string"
    required: bool = True
    description: str = ""


class OutputSpec(BaseModel):
    name: str
    type: str = "string"
    required: bool = True
    description: str = ""


class KnownOutcome(BaseModel):
    code: BusinessCode
    detect_text: str


class CompatibilityMeta(BaseModel):
    vendor: str = "Meridian"
    product: str = "MemberServ"
    version_range: str = ">=demo-1"
    required_features: list[str] = Field(
        default_factory=lambda: ["member-search", "accounts-table"]
    )
    tenants: list[str] = Field(default_factory=lambda: ["pine", "harbor"])


class RecoveryHint(BaseModel):
    code: str
    max_attempts: int = 1


class StepBase(BaseModel):
    step_id: str
    precondition: Checkpoint | None = None
    postcondition: Checkpoint | None = None
    timeout_ms: int = 8000
    effect: EffectClass = EffectClass.READ
    safe_to_repeat: bool = True
    recovery: RecoveryHint | None = None


class NavigateStep(StepBase):
    action: Literal["navigate"] = "navigate"
    url_template: str


class ClickStep(StepBase):
    action: Literal["click"] = "click"
    target: TargetDescriptor


class TypeStep(StepBase):
    action: Literal["type"] = "type"
    target: TargetDescriptor
    value_source: str


class ExtractStep(StepBase):
    action: Literal["extract"] = "extract"
    target: TargetDescriptor
    output_key: str


class AssertStep(StepBase):
    action: Literal["assert"] = "assert"
    checkpoint: Checkpoint


class DismissStep(StepBase):
    action: Literal["dismiss"] = "dismiss"
    target: TargetDescriptor


Step = Annotated[
    NavigateStep | ClickStep | TypeStep | ExtractStep | AssertStep | DismissStep,
    Field(discriminator="action"),
]

# Actions that become durable artifact steps and must be replayable.
COMPILABLE_ACTIONS: frozenset[str] = frozenset(
    {"navigate", "click", "type", "extract", "dismiss", "assert"}
)


class CapabilityArtifact(BaseModel):
    schema_version: str = SCHEMA_VERSION
    capability_id: str
    capability_version: str = "1"
    name: str
    description: str
    target_app: str = "Meridian MemberServ"
    vendor: str = "Meridian"
    product: str = "MemberServ"
    compatibility: CompatibilityMeta = Field(default_factory=CompatibilityMeta)
    risk: EffectClass = EffectClass.READ
    inputs: list[InputSpec] = Field(default_factory=list)
    outputs: list[OutputSpec] = Field(default_factory=list)
    steps: list[Step]
    final_checkpoint: Checkpoint
    known_outcomes: list[KnownOutcome] = Field(default_factory=list)
    approval_status: str = "approved"
    created_by: str = "CapabilityCompiler"


_STEP_ADAPTER: TypeAdapter[list[Step]] = TypeAdapter(list[Step])


def load_artifact(path: str | bytes) -> CapabilityArtifact:
    from pathlib import Path

    raw = Path(path).read_text(encoding="utf-8") if isinstance(path, str) else path.decode()
    data = yaml.safe_load(raw)
    return CapabilityArtifact.model_validate(data)


def dump_artifact(artifact: CapabilityArtifact) -> str:
    payload: dict[str, Any] = artifact.model_dump(mode="json", exclude_none=True)
    return yaml.safe_dump(_drop_empty(payload), sort_keys=False, allow_unicode=True)


def _drop_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _drop_empty(v) for k, v in value.items() if v not in ({}, [])}
    if isinstance(value, list):
        return [_drop_empty(v) for v in value]
    return value


def bind_parameters(source: str, params: dict[str, Any], *, base_url: str = "") -> str:
    if source.startswith("input:"):
        key = source.split(":", 1)[1]
        if key not in params:
            raise ValueError(f"missing input parameter: {key}")
        return str(params[key])
    if source.startswith("literal:"):
        return source.split(":", 1)[1]
    return source.format(base_url=base_url.rstrip("/"), **params)

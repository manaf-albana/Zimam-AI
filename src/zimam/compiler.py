from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from zimam.artifact import (
    SCHEMA_VERSION,
    CapabilityArtifact,
    Checkpoint,
    ClickStep,
    CompatibilityMeta,
    DismissStep,
    ExtractStep,
    InputSpec,
    KnownOutcome,
    NavigateStep,
    OutputSpec,
    Predicate,
    TargetDescriptor,
    TypeStep,
)
from zimam.observation import Control, Observation
from zimam.planner import AgentDecision
from zimam.policy import classify_effect
from zimam.redaction import Redactor
from zimam.results import BusinessCode, EffectClass


class DiscoveryTrace:
    def __init__(self, run_id: str, goal: str, model: str) -> None:
        self.run_id = run_id
        self.goal = goal
        self.model = model
        self.started_at = datetime.now(UTC).isoformat()
        self.steps: list[dict] = []

    def add(
        self,
        observation: Observation,
        decision: AgentDecision,
        executed: str,
        control: Control | None,
    ) -> None:
        self.steps.append(
            {
                "url": observation.url,
                "title": observation.title,
                "decision": decision.model_dump(),
                "executed": executed,
                "control": control.model_dump() if control else None,
                "screenshot_path": observation.screenshot_path,
            }
        )


def _descriptor(control: Control) -> TargetDescriptor:
    attrs = {k: v for k, v in control.stable_attributes.items() if v}
    return TargetDescriptor(
        role=control.role or None,
        accessible_name=control.accessible_name or None,
        label=control.label or None,
        text=None,
        frame=None if control.frame in {"", "main"} else control.frame,
        stable_attributes=attrs,
    )


def _member_id(goal: str) -> str | None:
    match = re.search(r"\b(\d{5})\b", goal)
    return match.group(1) if match else None


def _is_member_id_field(control: Control) -> bool:
    name = (control.accessible_name or "").lower().strip()
    label = (control.label or "").lower().strip()
    markers = ("member number", "member id", "member_id")
    return any(m == name or m == label or m in name or m in label for m in markers)


class CapabilityCompiler:
    def __init__(self, redactor: Redactor) -> None:
        self.redactor = redactor

    def compile(self, trace: DiscoveryTrace, *, tenant: str = "pine") -> CapabilityArtifact:
        steps: list = []
        member_id = _member_id(trace.goal)
        n = 1
        saw_navigate = False
        for record in trace.steps:
            decision = AgentDecision.model_validate(record["decision"])
            control = Control.model_validate(record["control"]) if record.get("control") else None
            if decision.action == "navigate":
                url = self.redactor.text(decision.value or record["url"])
                if member_id:
                    url = url.replace(member_id, "{member_id}")
                url = re.sub(r"https?://[^/]+", "{base_url}", url)
                path = urlparse(url.replace("{base_url}", "http://local")).path
                steps.append(
                    NavigateStep(
                        step_id=f"s{n}",
                        url_template=url if "{base_url}" in url else "{base_url}/" + tenant + "/",
                        effect=classify_effect("navigate", route=path),
                    )
                )
                saw_navigate = True
                n += 1
                continue
            if decision.action == "type" and control:
                if member_id and decision.value == member_id and _is_member_id_field(control):
                    source = "input:member_id"
                else:
                    source = f"literal:{decision.value}"
                target_name = control.accessible_name or ""
                steps.append(
                    TypeStep(
                        step_id=f"s{n}",
                        target=_descriptor(control),
                        value_source=source,
                        effect=classify_effect("type", target_name=target_name),
                    )
                )
                n += 1
            elif decision.action == "click" and control:
                post = None
                target_name = control.accessible_name or ""
                if target_name.lower() == "search":
                    post = Checkpoint(
                        mode="any",
                        predicates=[
                            Predicate(kind="route_matches", pattern=r"/member/"),
                            Predicate(kind="text_present", text="Member not found"),
                            Predicate(kind="text_present", text="Invalid member"),
                            Predicate(kind="text_present", text="You do not have permission"),
                            Predicate(kind="text_present", text="session has expired"),
                            Predicate(kind="text_present", text="Application error"),
                            Predicate(kind="text_present", text="Temporarily unavailable"),
                            Predicate(kind="text_present", text="Scheduled maintenance"),
                        ],
                    )
                steps.append(
                    ClickStep(
                        step_id=f"s{n}",
                        target=_descriptor(control),
                        postcondition=post,
                        effect=classify_effect(
                            "click",
                            target_name=target_name,
                            route=urlparse(record["url"]).path,
                        ),
                    )
                )
                n += 1
            elif decision.action == "dismiss" and control:
                target_name = control.accessible_name or ""
                steps.append(
                    DismissStep(
                        step_id=f"s{n}",
                        target=_descriptor(control),
                        effect=classify_effect("dismiss", target_name=target_name),
                    )
                )
                n += 1
            elif decision.action == "extract" and control:
                steps.append(
                    ExtractStep(
                        step_id=f"s{n}",
                        target=_descriptor(control),
                        output_key="savings_balance",
                        effect=EffectClass.READ,
                    )
                )
                n += 1
        if not saw_navigate:
            steps.insert(
                0,
                NavigateStep(
                    step_id="s0",
                    url_template="{base_url}/" + tenant + "/",
                    effect=EffectClass.READ,
                ),
            )
        steps = _complete_lookup_steps(steps)
        for i, step in enumerate(steps, start=1):
            step.step_id = f"s{i}"
        return CapabilityArtifact(
            schema_version=SCHEMA_VERSION,
            capability_id="lookup_savings_balance",
            capability_version="1",
            name="Lookup savings balance",
            description="Look up a member and return the current savings balance.",
            compatibility=CompatibilityMeta(
                tenants=[tenant, "harbor"] if tenant == "pine" else [tenant, "pine"]
            ),
            risk=EffectClass.READ,
            inputs=[InputSpec(name="member_id", type="string", description="Five-digit member id")],
            outputs=[
                OutputSpec(name="savings_balance", type="money"),
                OutputSpec(name="member_name", type="string", required=False),
            ],
            steps=steps,
            final_checkpoint=Checkpoint(
                mode="all",
                predicates=[
                    Predicate(kind="text_present", text="Current balance"),
                    Predicate(kind="route_matches", pattern=r"savings"),
                ],
            ),
            known_outcomes=[
                KnownOutcome(code=BusinessCode.MEMBER_NOT_FOUND, detect_text="Member not found"),
                KnownOutcome(
                    code=BusinessCode.SAVINGS_ACCOUNT_NOT_FOUND, detect_text="No savings account"
                ),
                KnownOutcome(code=BusinessCode.VALIDATION_REJECTED, detect_text="Invalid member"),
                KnownOutcome(
                    code=BusinessCode.PERMISSION_DENIED, detect_text="You do not have permission"
                ),
            ],
            created_by="CapabilityCompiler",
        )


def _complete_lookup_steps(steps: list) -> list:
    """Muse may finish once the balance is visible in the accounts table.

    Replay still needs an explicit Savings click + extract so the artifact
    is reusable without the model.
    """
    names = {
        (s.target.accessible_name or "").lower() for s in steps if hasattr(s, "target") and s.target
    }
    n = len(steps) + 1
    if "accounts" in names and "savings" not in names:
        steps.append(
            ClickStep(
                step_id=f"s{n}",
                target=TargetDescriptor(role="link", accessible_name="Savings"),
                postcondition=Checkpoint(
                    mode="any",
                    predicates=[
                        Predicate(kind="route_matches", pattern=r"savings"),
                        Predicate(kind="text_present", text="No savings account"),
                    ],
                ),
            )
        )
        n += 1
    extract_keys = {s.output_key for s in steps if isinstance(s, ExtractStep)}
    if "savings_balance" not in extract_keys and ("savings" in names or "accounts" in names):
        steps.append(
            ExtractStep(
                step_id=f"s{n}",
                target=TargetDescriptor(
                    role="status",
                    accessible_name="Current balance",
                    stable_attributes={"data-extract": "savings_balance"},
                ),
                output_key="savings_balance",
            )
        )
        n += 1
    if "member_name" not in extract_keys and ("savings" in names or "accounts" in names):
        steps.append(
            ExtractStep(
                step_id=f"s{n}",
                target=TargetDescriptor(
                    role="status",
                    accessible_name="Member name",
                    stable_attributes={"data-extract": "member_name"},
                ),
                output_key="member_name",
            )
        )
    return steps

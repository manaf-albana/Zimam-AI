from __future__ import annotations

import time
from urllib.parse import urlparse

from zimam.artifact import (
    SUPPORTED_SCHEMA_VERSIONS,
    CapabilityArtifact,
    ClickStep,
    DismissStep,
    ExtractStep,
    NavigateStep,
    TargetDescriptor,
    TypeStep,
    bind_parameters,
)
from zimam.checkpoints import CheckpointFailure, PageView, evaluate_checkpoint, wait_until
from zimam.compatibility import CompatibilityChecker, CompatStatus, TenantOverride
from zimam.discovery import detect_business_outcome, detect_unknown_dialog
from zimam.evidence import EvidenceLog
from zimam.policy import PolicyEngine
from zimam.results import (
    BusinessOutcomeResult,
    EffectClass,
    FailureCode,
    FailureContext,
    FailureResult,
    HumanCode,
    HumanRequiredResult,
    RunResult,
    SuccessResult,
)
from zimam.sessions import ControlSession, StaleGenerationError
from zimam.surfaces import BrowserSurface
from zimam.targeting import TargetResolver

KNOWN_INTERSTITIAL = "scheduled maintenance"
TRANSIENT_BACKEND = "temporarily unavailable"

# Actions ReplayEngine executes from artifacts (must stay in sync with compiler).
REPLAYABLE_ACTIONS: frozenset[str] = frozenset({"navigate", "click", "type", "extract", "dismiss"})


class ReplayEngine:
    def __init__(
        self,
        surface: BrowserSurface,
        policy: PolicyEngine,
        control: ControlSession,
        evidence: EvidenceLog,
        *,
        override: TenantOverride | None = None,
        model_calls: int = 0,
    ) -> None:
        self.surface = surface
        self.policy = policy
        self.control = control
        self.evidence = evidence
        self.override = override
        self.resolver = TargetResolver()
        self.model_calls = model_calls
        self.compat = CompatibilityChecker()
        self.drift: list[str] = []

    def run(
        self,
        artifact: CapabilityArtifact,
        params: dict[str, str],
        *,
        run_id: str,
        base_url: str,
        tenant: str,
    ) -> RunResult:
        started = time.monotonic()
        self.evidence.event(
            "RUN_STARTED", run_id=run_id, mode="REPLAY", capability=artifact.capability_id
        )
        invalid = self._validate(artifact, params, tenant)
        if invalid:
            return invalid
        outputs: dict[str, str] = {}
        last_checkpoint = ""
        try:
            for step in artifact.steps:
                self.control.require_automation(self.control.record.generation)
                self.control.update(step=step.step_id, last_action=step.action, run_id=run_id)
                if self.surface.page.url not in {"", "about:blank"}:
                    recovered = self._recover_if_needed(run_id)
                    if recovered is not None:
                        return self._with_timing(recovered, started)
                    terminal = self._terminal_state(run_id, artifact, step.step_id, last_checkpoint)
                    if terminal:
                        return self._with_timing(terminal, started)
                    outcome = self._business()
                    if outcome:
                        self.evidence.event("BUSINESS_OUTCOME", run_id=run_id, code=outcome.code)
                        return self._with_timing(outcome, started)
                if step.precondition:
                    self._check(step.precondition, step.step_id, run_id, artifact)
                    last_checkpoint = f"{step.step_id}:pre"
                if isinstance(step, NavigateStep):
                    url = bind_parameters(step.url_template, params, base_url=base_url)
                    if self.override and self.override.route_prefix:
                        url = url.replace("/pine/", self.override.route_prefix.rstrip("/") + "/")
                    parsed = urlparse(url)
                    origin = f"{parsed.scheme}://{parsed.netloc}"
                    origin_verdict = self.policy.check_origin(origin)
                    if not origin_verdict.allowed:
                        return self._fail(
                            run_id,
                            artifact,
                            step.step_id,
                            FailureCode.POLICY_VIOLATION,
                            origin_verdict.reason,
                            last_checkpoint,
                        )
                    path = parsed.path
                    verdict = self.policy.check_action("navigate", effect=step.effect, route=path)
                    self.evidence.event("POLICY_CHECK", run_id=run_id, allowed=verdict.allowed)
                    if not verdict.allowed:
                        return self._fail(
                            run_id,
                            artifact,
                            step.step_id,
                            FailureCode.POLICY_VIOLATION,
                            verdict.reason,
                            last_checkpoint,
                        )
                    self.surface.execute("navigate", None, url, self.control.record.generation)
                elif isinstance(step, TypeStep):
                    value = bind_parameters(step.value_source, params, base_url=base_url)
                    acted = self._act(
                        step.target,
                        "type",
                        value,
                        step.step_id,
                        run_id,
                        artifact,
                        last_checkpoint,
                        effect=step.effect,
                    )
                    if isinstance(acted, RunResult):
                        return self._with_timing(acted, started)
                elif isinstance(step, ClickStep | DismissStep):
                    acted = self._act(
                        step.target,
                        "click",
                        None,
                        step.step_id,
                        run_id,
                        artifact,
                        last_checkpoint,
                        effect=step.effect,
                    )
                    if isinstance(acted, RunResult):
                        return self._with_timing(acted, started)
                elif isinstance(step, ExtractStep):
                    acted = self._act(
                        step.target,
                        "extract",
                        None,
                        step.step_id,
                        run_id,
                        artifact,
                        last_checkpoint,
                        effect=step.effect,
                    )
                    if isinstance(acted, RunResult):
                        return self._with_timing(acted, started)
                    outputs[step.output_key] = str(acted)
                if step.postcondition:
                    wait_until(
                        lambda s=step: self._checkpoint_ok(s.postcondition),
                        step.timeout_ms,
                    )
                    self._check(step.postcondition, step.step_id, run_id, artifact)
                    last_checkpoint = f"{step.step_id}:post"
                    self.evidence.event("CHECKPOINT_PASSED", run_id=run_id, step=step.step_id)
                outcome = self._business()
                if outcome:
                    self.evidence.event("BUSINESS_OUTCOME", run_id=run_id, code=outcome.code)
                    return self._with_timing(outcome, started)
            self._check(artifact.final_checkpoint, "final", run_id, artifact)
            last_checkpoint = "final"
            result = SuccessResult(
                run_id=run_id,
                outputs=outputs,
                model_calls=self.model_calls,
                evidence_dir=str(self.evidence.directory),
            )
            self.evidence.event("RUN_SUCCEEDED", run_id=run_id, outputs=outputs, model_calls=0)
            return self._with_timing(result, started)
        except CheckpointFailure as exc:
            return self._with_timing(
                self._fail(
                    run_id,
                    artifact,
                    "checkpoint",
                    FailureCode.POSTCONDITION_FAILED,
                    str(exc),
                    last_checkpoint,
                    expected=exc.expected,
                    observed=exc.observed,
                ),
                started,
            )
        except StaleGenerationError as exc:
            return self._with_timing(
                self._fail(
                    run_id, artifact, None, FailureCode.SESSION_LOST, str(exc), last_checkpoint
                ),
                started,
            )

    def _validate(
        self, artifact: CapabilityArtifact, params: dict[str, str], tenant: str
    ) -> RunResult | None:
        if artifact.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            return self._fail(
                "na",
                artifact,
                None,
                FailureCode.UNSUPPORTED_ARTIFACT_VERSION,
                f"schema {artifact.schema_version}",
                "",
            )
        for spec in artifact.inputs:
            if spec.required and spec.name not in params:
                return self._fail(
                    "na", artifact, None, FailureCode.ARTIFACT_INVALID, f"missing {spec.name}", ""
                )
        status = self.compat.check(
            vendor=artifact.vendor,
            product=artifact.product,
            tenant=tenant,
            override=self.override,
            recorded_tenants=artifact.compatibility.tenants,
        )
        if status is CompatStatus.INCOMPATIBLE:
            return self._fail(
                "na", artifact, None, FailureCode.INCOMPATIBLE_CAPABILITY, status.value, ""
            )
        if status is CompatStatus.SUPPORTED_WITH_OVERRIDE:
            self.drift.append("override_profile_used")
        return None

    def _apply_override(self, target: TargetDescriptor) -> TargetDescriptor:
        if not self.override:
            return target
        data = target.model_dump()
        if target.frame and target.frame in self.override.frame_overrides:
            data["frame"] = self.override.frame_overrides[target.frame]
        for patch in self.override.target_overrides.values():
            if target.accessible_name and "accessible_name" in patch:
                if target.accessible_name.lower() in {"member number", "member id"}:
                    data["accessible_name"] = patch["accessible_name"]
                    data["label"] = patch.get("label", patch["accessible_name"])
        return TargetDescriptor.model_validate(data)

    def _act(
        self,
        target: TargetDescriptor,
        action: str,
        value: str | None,
        step_id: str,
        run_id: str,
        artifact: CapabilityArtifact,
        last_checkpoint: str,
        *,
        effect: EffectClass,
    ) -> str | RunResult:
        target = self._apply_override(target)
        self.surface.observe(goal="", step_index=0, budget=0, last_result="")
        parsed = urlparse(self.surface.page.url)
        if parsed.scheme and parsed.netloc:
            origin_verdict = self.policy.check_origin(f"{parsed.scheme}://{parsed.netloc}")
            if not origin_verdict.allowed:
                return self._fail(
                    run_id,
                    artifact,
                    step_id,
                    FailureCode.POLICY_VIOLATION,
                    origin_verdict.reason,
                    last_checkpoint,
                )
        resolution = self.resolver.resolve(target, self.surface.candidates())
        self.evidence.event(
            "TARGET_RESOLVED",
            run_id=run_id,
            strategy=resolution.strategy,
            candidates=resolution.candidate_count,
            score=resolution.score,
            ok=resolution.ok,
        )
        if resolution.used_fallback:
            self.drift.append("fallback_locator")
        if not resolution.ok:
            if resolution.code is HumanCode.TARGET_AMBIGUOUS:
                return HumanRequiredResult(
                    run_id=run_id,
                    code=HumanCode.TARGET_AMBIGUOUS,
                    message=resolution.reason,
                    model_calls=0,
                )
            return self._fail(
                run_id,
                artifact,
                step_id,
                FailureCode.TARGET_NOT_RESOLVED,
                resolution.reason,
                last_checkpoint,
            )
        name = resolution.winner.accessible_name if resolution.winner else ""
        verdict = self.policy.check_action(
            action,
            effect=effect,
            target_name=name,
            route=parsed.path,
        )
        if verdict.requires_human:
            return HumanRequiredResult(
                run_id=run_id,
                code=HumanCode.RISKY_ACTION_REQUIRES_APPROVAL,
                message=verdict.reason,
                model_calls=0,
            )
        if not verdict.allowed:
            return self._fail(
                run_id,
                artifact,
                step_id,
                FailureCode.POLICY_VIOLATION,
                verdict.reason,
                last_checkpoint,
            )
        handle = resolution.winner.handle if resolution.winner else None
        synthetic = f"replay-{step_id}"
        self.surface._handles[synthetic] = handle
        self.evidence.event("ACTION_STARTED", run_id=run_id, step=step_id, action=action)
        executed = self.surface.execute(action, synthetic, value, self.control.record.generation)
        self.evidence.event("ACTION_COMPLETED", run_id=run_id, step=step_id)
        return executed

    def _terminal_state(
        self, run_id: str, artifact: CapabilityArtifact, step_id: str, last_checkpoint: str
    ) -> RunResult | None:
        view = self._view()
        text = view.text.lower()
        if "session has expired" in text:
            return self._fail(
                run_id,
                artifact,
                step_id,
                FailureCode.SESSION_LOST,
                "session expired",
                last_checkpoint,
            )
        if "ora-01403" in text or "application error" in text:
            return self._fail(
                run_id,
                artifact,
                step_id,
                FailureCode.UNEXPECTED_APPLICATION_STATE,
                "hard application failure",
                last_checkpoint,
                observed="crash page",
            )
        return None

    def _view(self) -> PageView:
        obs = self.surface.observe(goal="", step_index=0, budget=0, last_result="")
        return PageView(obs.url, obs.title, obs.body_text, obs.dialogs, self.surface.candidates())

    def _checkpoint_ok(self, checkpoint) -> bool:
        try:
            evaluate_checkpoint(checkpoint, self._view(), self.resolver)
            return True
        except CheckpointFailure:
            return False

    def _check(self, checkpoint, step_id, run_id, artifact) -> None:
        evaluate_checkpoint(checkpoint, self._view(), self.resolver)

    def _business(self) -> BusinessOutcomeResult | None:
        view = self._view()
        code = detect_business_outcome(view.text)
        if code:
            return BusinessOutcomeResult(
                run_id=self.control.record.run_id or "replay",
                code=code,
                message=code.value,
                model_calls=0,
            )
        return None

    def _recover_if_needed(self, run_id: str) -> RunResult | None:
        view = self._view()
        if detect_unknown_dialog(view.dialogs):
            return HumanRequiredResult(
                run_id=run_id,
                code=HumanCode.UNKNOWN_DIALOG,
                message=view.dialogs[0] if view.dialogs else "unknown dialog",
                model_calls=0,
            )
        text = view.text.lower()
        if KNOWN_INTERSTITIAL in text:
            self.evidence.event("RECOVERY_STARTED", run_id=run_id, code="KNOWN_INTERSTITIAL")
            continue_btn = next(
                (
                    c
                    for c in view.candidates
                    if c.accessible_name.lower() in {"continue", "dismiss", "ok"}
                ),
                None,
            )
            if continue_btn is None:
                return HumanRequiredResult(
                    run_id=run_id,
                    code=HumanCode.UNKNOWN_DIALOG,
                    message="interstitial without dismiss",
                    model_calls=0,
                )
            synthetic = "recover-dismiss"
            self.surface._handles[synthetic] = continue_btn.handle
            self.surface.execute("click", synthetic, None, self.control.record.generation)
            self.evidence.event("RECOVERY_COMPLETED", run_id=run_id, code="KNOWN_INTERSTITIAL")
            return None
        if TRANSIENT_BACKEND in text:
            self.evidence.event("RECOVERY_STARTED", run_id=run_id, code="RETRYABLE_BACKEND_FAILURE")
            retry = next((c for c in view.candidates if c.accessible_name.lower() == "retry"), None)
            if retry:
                self.surface._handles["recover-retry"] = retry.handle
                self.surface.execute("click", "recover-retry", None, self.control.record.generation)
                self.evidence.event(
                    "RECOVERY_COMPLETED", run_id=run_id, code="RETRYABLE_BACKEND_FAILURE"
                )
            return None
        return None

    def _fail(
        self,
        run_id: str,
        artifact: CapabilityArtifact,
        step_id: str | None,
        code: FailureCode,
        message: str,
        last_checkpoint: str,
        expected: str | None = None,
        observed: str | None = None,
    ) -> FailureResult:
        shot = self.evidence.screenshot_path("failure.png")
        try:
            self.surface.capture_evidence(shot)
            refs = [str(shot)]
        except Exception:
            refs = []
        self.evidence.event("RUN_FAILED", run_id=run_id, code=code, message=message)
        return FailureResult(
            run_id=run_id,
            code=code,
            context=FailureContext(
                run_id=run_id,
                capability_id=artifact.capability_id,
                capability_version=artifact.capability_version,
                step_id=step_id,
                code=code.value,
                message=message,
                expected=expected,
                observed=observed,
                last_checkpoint=last_checkpoint or None,
                evidence_refs=refs,
            ),
            model_calls=0,
            evidence_dir=str(self.evidence.directory),
        )

    def _with_timing(self, result: RunResult, started: float) -> RunResult:
        result.duration_ms = int((time.monotonic() - started) * 1000)
        result.model_calls = 0
        return result

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:  # pragma: no cover - allows non-browser imports when Playwright is absent
    PlaywrightError = RuntimeError  # type: ignore[misc, assignment]
    PlaywrightTimeoutError = TimeoutError  # type: ignore[misc, assignment]

from zimam.compiler import DiscoveryTrace
from zimam.evidence import EvidenceLog
from zimam.observation import Observation
from zimam.planner import AgentDecision, DiscoveryPlanner
from zimam.policy import PolicyEngine, classify_effect
from zimam.providers.nvidia import ProviderRateLimited, ProviderTemporaryFailure
from zimam.results import (
    BusinessCode,
    BusinessOutcomeResult,
    FailureCode,
    FailureContext,
    FailureResult,
    HumanCode,
    HumanRequiredResult,
    RunResult,
    SuccessResult,
)
from zimam.sessions import ControlSession, Owner, StaleGenerationError
from zimam.surfaces import BrowserSurface


class StuckDetector:
    def __init__(self) -> None:
        self.same_obs = 0
        self.failed = 0
        self.malformed = 0
        self.ambiguous = 0
        self.unknown_modal = 0
        self._last_hash = ""

    def note_observation(self, observation: Observation) -> None:
        digest = hashlib.sha256(
            f"{observation.url}|{observation.last_result}|{[(c.accessible_name, c.text) for c in observation.controls]}".encode()
        ).hexdigest()
        if digest == self._last_hash:
            self.same_obs += 1
        else:
            self.same_obs = 0
        self._last_hash = digest

    def stuck(self) -> str | None:
        if self.same_obs >= 4:
            return "repeated observation"
        if self.failed >= 3:
            return "repeated failed action"
        if self.malformed >= 3:
            return "repeated malformed action"
        if self.ambiguous >= 2:
            return "repeated ambiguity"
        if self.unknown_modal >= 1:
            return "unknown modal"
        return None


def detect_business_outcome(text: str) -> BusinessCode | None:
    lowered = text.lower()
    if "member not found" in lowered:
        return BusinessCode.MEMBER_NOT_FOUND
    if "no savings account" in lowered:
        return BusinessCode.SAVINGS_ACCOUNT_NOT_FOUND
    if "invalid member" in lowered:
        return BusinessCode.VALIDATION_REJECTED
    if "you do not have permission" in lowered:
        return BusinessCode.PERMISSION_DENIED
    return None


def detect_unknown_dialog(dialogs: list[str]) -> bool:
    known = ("scheduled maintenance", "please wait", "retry")
    for dialog in dialogs:
        low = dialog.lower()
        if not low.strip():
            continue
        if any(k in low for k in known):
            continue
        if "unexpected" in low or "unknown" in low or "contact operations" in low:
            return True
    return False


class DiscoveryEngine:
    def __init__(
        self,
        surface: BrowserSurface,
        planner: DiscoveryPlanner,
        policy: PolicyEngine,
        control: ControlSession,
        evidence: EvidenceLog,
        *,
        max_steps: int = 20,
    ) -> None:
        self.surface = surface
        self.planner = planner
        self.policy = policy
        self.control = control
        self.evidence = evidence
        self.max_steps = max_steps

    def run(self, goal: str, start_url: str, run_id: str) -> tuple[RunResult, DiscoveryTrace]:
        started = time.monotonic()
        trace = DiscoveryTrace(run_id, goal, getattr(self.planner, "model_name", "unknown"))
        stuck = StuckDetector()
        last = ""
        model_calls = 0
        self.evidence.event("RUN_STARTED", run_id=run_id, mode="DISCOVERY", goal=goal)
        self.control.update(run_id=run_id, mode="DISCOVERY", goal=goal)
        try:
            parsed = urlparse(start_url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            origin_verdict = self.policy.check_origin(origin)
            if not origin_verdict.allowed:
                return self._fail(
                    run_id,
                    FailureCode.POLICY_VIOLATION,
                    origin_verdict.reason,
                    model_calls,
                    started,
                ), trace
            effect = classify_effect("navigate", route=parsed.path)
            nav = self.policy.check_action("navigate", effect=effect, route=parsed.path)
            if not nav.allowed:
                return self._fail(
                    run_id, FailureCode.POLICY_VIOLATION, nav.reason, model_calls, started
                ), trace
            self.surface.execute("navigate", None, start_url, self.control.record.generation)
            last = f"navigated {start_url}"
        except (PlaywrightTimeoutError, PlaywrightError, OSError) as exc:
            return self._fail(
                run_id,
                FailureCode.UNEXPECTED_APPLICATION_STATE,
                str(exc),
                model_calls,
                started,
            ), trace

        for step in range(self.max_steps):
            if self.control.record.owner != Owner.AUTOMATION:
                return (
                    self._timed(
                        HumanRequiredResult(
                            run_id=run_id,
                            code=HumanCode.DISCOVERY_STUCK,
                            message="session is not owned by automation",
                            model_calls=model_calls,
                        ),
                        started,
                    ),
                    trace,
                )
            obs = self.surface.observe(
                goal=goal, step_index=step, budget=self.max_steps - step, last_result=last
            )
            shot = self.evidence.screenshot_path(f"step-{step:02d}.png")
            self.surface.capture_evidence(shot)
            obs.screenshot_path = str(shot)
            live_shot = Path("evidence/live/shot.png")
            live_shot.parent.mkdir(parents=True, exist_ok=True)
            if shot.exists() and shot.stat().st_size:
                live_shot.write_bytes(shot.read_bytes())
            self.control.update(url=obs.url, screenshot="/console/api/screenshot")
            self.evidence.event(
                "OBSERVATION_CAPTURED", run_id=run_id, url=obs.url, controls=len(obs.controls)
            )
            stuck.note_observation(obs)
            why = stuck.stuck()
            if why:
                self.evidence.event("INTERVENTION_REQUESTED", run_id=run_id, reason=why)
                return (
                    self._timed(
                        HumanRequiredResult(
                            run_id=run_id,
                            code=HumanCode.DISCOVERY_STUCK,
                            message=why,
                            model_calls=model_calls,
                        ),
                        started,
                    ),
                    trace,
                )
            if detect_unknown_dialog(obs.dialogs):
                stuck.unknown_modal += 1
                return (
                    self._timed(
                        HumanRequiredResult(
                            run_id=run_id,
                            code=HumanCode.UNKNOWN_DIALOG,
                            message=obs.dialogs[0],
                            observed=obs.dialogs[0],
                            model_calls=model_calls,
                        ),
                        started,
                    ),
                    trace,
                )
            outcome = detect_business_outcome(obs.body_text)
            if outcome:
                self.evidence.event("BUSINESS_OUTCOME", run_id=run_id, code=outcome)
                return (
                    self._timed(
                        BusinessOutcomeResult(
                            run_id=run_id,
                            code=outcome,
                            message=outcome.value,
                            model_calls=model_calls,
                        ),
                        started,
                    ),
                    trace,
                )

            try:
                self.evidence.event("MODEL_REQUEST", run_id=run_id, model=self.planner.model_name)
                decision = self.planner.decide(
                    obs,
                    goal,
                    [AgentDecision.model_validate(s["decision"]) for s in trace.steps],
                    "SAFE_READ allowed",
                )
                model_calls += 1
            except (
                ValueError,
                ProviderTemporaryFailure,
                ProviderRateLimited,
            ) as exc:
                stuck.malformed += 1
                last = f"planner error {type(exc).__name__}"
                self.evidence.event(
                    "MODEL_DECISION",
                    run_id=run_id,
                    error=type(exc).__name__,
                    detail=str(exc)[:240],
                )
                continue
            self.evidence.event(
                "MODEL_DECISION", run_id=run_id, action=decision.action, target=decision.target_ref
            )

            if decision.human_required or decision.action == "request_human":
                self.control.transfer_to_human(decision.rationale)
                self.evidence.event(
                    "INTERVENTION_REQUESTED", run_id=run_id, reason=decision.rationale
                )
                return (
                    self._timed(
                        HumanRequiredResult(
                            run_id=run_id,
                            code=HumanCode.DISCOVERY_STUCK
                            if "stuck" in decision.rationale.lower()
                            else HumanCode.RISKY_ACTION_REQUIRES_APPROVAL,
                            message=decision.rationale,
                            model_calls=model_calls,
                        ),
                        started,
                    ),
                    trace,
                )
            if decision.goal_complete or decision.action == "finish":
                outputs = decision.extraction or {}
                if not outputs:
                    outputs = _outputs_from_obs(obs)
                trace.add(obs, decision, "finish", None)
                self.evidence.event("RUN_SUCCEEDED", run_id=run_id, outputs=outputs)
                return (
                    self._timed(
                        SuccessResult(run_id=run_id, outputs=outputs, model_calls=model_calls),
                        started,
                    ),
                    trace,
                )

            control = next((c for c in obs.controls if c.id == decision.target_ref), None)
            target_name = control.accessible_name if control else ""
            parsed_obs = urlparse(obs.url)
            page_origin = f"{parsed_obs.scheme}://{parsed_obs.netloc}" if parsed_obs.netloc else ""
            if page_origin:
                origin_verdict = self.policy.check_origin(page_origin)
                if not origin_verdict.allowed:
                    return self._fail(
                        run_id,
                        FailureCode.POLICY_VIOLATION,
                        origin_verdict.reason,
                        model_calls,
                        started,
                    ), trace
            path = parsed_obs.path
            if decision.action == "navigate" and decision.value:
                nav_parsed = urlparse(decision.value)
                nav_origin = f"{nav_parsed.scheme}://{nav_parsed.netloc}"
                if nav_parsed.scheme and nav_parsed.netloc:
                    nav_origin_verdict = self.policy.check_origin(nav_origin)
                    if not nav_origin_verdict.allowed:
                        return self._fail(
                            run_id,
                            FailureCode.POLICY_VIOLATION,
                            nav_origin_verdict.reason,
                            model_calls,
                            started,
                        ), trace
                    path = nav_parsed.path
            effect = classify_effect(decision.action, target_name=target_name, route=path)
            verdict = self.policy.check_action(
                decision.action, effect=effect, target_name=target_name, route=path
            )
            self.evidence.event(
                "POLICY_CHECK",
                run_id=run_id,
                allowed=verdict.allowed,
                reason=verdict.reason,
                effect=effect.value,
            )
            if verdict.requires_human:
                self.control.transfer_to_human(verdict.reason)
                return (
                    self._timed(
                        HumanRequiredResult(
                            run_id=run_id,
                            code=HumanCode.RISKY_ACTION_REQUIRES_APPROVAL,
                            message=verdict.reason,
                            model_calls=model_calls,
                        ),
                        started,
                    ),
                    trace,
                )
            if not verdict.allowed:
                return self._fail(
                    run_id, FailureCode.POLICY_VIOLATION, verdict.reason, model_calls, started
                ), trace
            try:
                executed = self.surface.execute(
                    decision.action,
                    decision.target_ref,
                    decision.value,
                    self.control.record.generation,
                )
                last = executed
                stuck.failed = 0
            except StaleGenerationError as exc:
                return self._fail(
                    run_id, FailureCode.SESSION_LOST, str(exc), model_calls, started
                ), trace
            except (PlaywrightTimeoutError, PlaywrightError, LookupError) as exc:
                stuck.failed += 1
                last = f"failed {exc}"
                executed = last
            trace.add(obs, decision, executed, control)
            self.evidence.event("ACTION_COMPLETED", run_id=run_id, result=executed)
            self.control.update(
                url=self.surface.page.url, last_action=executed, step=f"{step + 1}/{self.max_steps}"
            )

        return (
            self._timed(
                HumanRequiredResult(
                    run_id=run_id,
                    code=HumanCode.DISCOVERY_STUCK,
                    message="max steps reached",
                    model_calls=model_calls,
                ),
                started,
            ),
            trace,
        )

    def _fail(
        self,
        run_id: str,
        code: FailureCode,
        message: str,
        model_calls: int,
        started: float,
    ) -> FailureResult:
        self.evidence.event("RUN_FAILED", run_id=run_id, code=code, message=message)
        result = FailureResult(
            run_id=run_id,
            code=code,
            context=FailureContext(run_id=run_id, code=code.value, message=message),
            model_calls=model_calls,
        )
        result.duration_ms = int((time.monotonic() - started) * 1000)
        return result

    def _timed(self, result: RunResult, started: float) -> RunResult:
        result.duration_ms = int((time.monotonic() - started) * 1000)
        return result


def _outputs_from_obs(obs: Observation) -> dict[str, Any]:
    import re

    match = re.search(r"\$[\d,]+\.\d{2}", obs.body_text)
    name = ""
    for line in obs.body_text.splitlines():
        if line.lower().startswith("member:") or "member name" in line.lower():
            name = line.split(":", 1)[-1].strip()
    out: dict[str, Any] = {}
    if match:
        out["savings_balance"] = match.group(0)
    if name:
        out["member_name"] = name
    return out

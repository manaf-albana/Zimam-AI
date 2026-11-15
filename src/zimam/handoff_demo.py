from __future__ import annotations

import time
import uuid

from zimam.evidence import EvidenceLog
from zimam.results import HumanCode, HumanRequiredResult, RunResult, SuccessResult
from zimam.runtime import ensure_app
from zimam.sessions import ControlSession, SessionStore, StaleGenerationError
from zimam.settings import Settings
from zimam.surfaces import attach_surface, launch_browser


def run_handoff(settings: Settings, *, auto_resume: bool = False) -> RunResult:
    """Unknown-dialog pause on the SAME Chromium session, then resume."""
    ensure_app(settings)
    run_id = uuid.uuid4().hex[:12]
    from zimam.redaction import Redactor

    redactor = Redactor([settings.nvidia_api_key] if settings.nvidia_api_key else [])
    evidence = EvidenceLog(settings.evidence_dir / "handoff", redactor, reset=True)
    store = SessionStore(settings.evidence_dir / "live" / "state.json")
    control = ControlSession(run_id, store)
    runtime = launch_browser(headed=settings.headed, persistent=True)
    surface = attach_surface(runtime, control)
    start = f"{settings.bank_base_url.rstrip('/')}/pine/"
    identity_before = surface.session_state()
    try:
        surface.execute("navigate", None, start, control.record.generation)
        obs = surface.observe(goal="handoff", step_index=0, budget=8, last_result="")
        box = next(c for c in obs.controls if c.accessible_name in {"Member Number", "Member ID"})
        surface.execute("type", box.id, "70001", control.record.generation)
        obs = surface.observe(goal="handoff", step_index=1, budget=7, last_result="typed")
        search = next(
            c
            for c in obs.controls
            if c.role == "button" and c.accessible_name == "Search" and c.frame == box.frame
        )
        surface.execute("click", search.id, None, control.record.generation)
        surface.wait_for_load()
        obs = surface.observe(goal="handoff", step_index=2, budget=6, last_result="clicked search")
        shot = evidence.screenshot_path("paused.png")
        surface.capture_evidence(shot)
        old_gen = control.record.generation
        control.update(
            url=surface.page.url,
            goal="Resolve unknown dialog",
            screenshot="/console/api/screenshot",
            observed="; ".join(obs.dialogs) or obs.body_text[:180],
            expected="Member profile without unknown dialog",
        )
        control.request_intervention("UNKNOWN_DIALOG")
        evidence.event(
            "INTERVENTION_REQUESTED",
            owner=control.record.owner.value,
            generation=control.record.generation,
            surface_session_id=identity_before["surface_session_id"],
            context_id=identity_before["context_id"],
            page_id=identity_before["page_id"],
        )
        try:
            surface.execute("click", search.id, None, old_gen)
            stale_rejected = False
        except StaleGenerationError:
            stale_rejected = True
        evidence.event(
            "HUMAN_ACTION", detail="stale automation click attempted", rejected=stale_rejected
        )
        if auto_resume or not settings.headed:
            control.transfer_to_human("UNKNOWN_DIALOG")
            evidence.event(
                "CONTROL_TRANSFERRED", owner="HUMAN", generation=control.record.generation
            )
            ack = next(
                (c for c in obs.controls if "acknowledge" in c.accessible_name.lower()), None
            )
            if ack:
                control.record_human_action("clicked Acknowledge")
                surface.page.get_by_role("button", name="Acknowledge").click()
            control.resume_automation()
            evidence.event("AUTOMATION_RESUMED", generation=control.record.generation)
            surface.observe(goal="handoff", step_index=3, budget=5, last_result="resumed")
            identity_after = surface.session_state()
            same = (
                identity_before["surface_session_id"] == identity_after["surface_session_id"]
                and identity_before["context_id"] == identity_after["context_id"]
                and identity_before["page_id"] == identity_after["page_id"]
            )
            result = SuccessResult(
                run_id=run_id,
                outputs={
                    "owner_after": control.record.owner.value,
                    "generation": str(control.record.generation),
                    "stale_rejected": "true" if stale_rejected else "false",
                    "same_session": "true" if same else "false",
                    "surface_session_id": identity_after["surface_session_id"],
                    "context_id": identity_after["context_id"],
                    "page_id": identity_after["page_id"],
                    "identity_before": identity_before["surface_session_id"],
                    "identity_after": identity_after["surface_session_id"],
                },
                model_calls=0,
            )
        else:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                cmd = store.take_command()
                if cmd and cmd.action == "take_control" and control.record.owner.value != "HUMAN":
                    control.transfer_to_human("operator take control")
                    control.record_human_action("Take Control")
                    evidence.event(
                        "CONTROL_TRANSFERRED",
                        owner="HUMAN",
                        generation=control.record.generation,
                    )
                if cmd and cmd.action == "resume":
                    control.record_human_action("operator resumed")
                    control.resume_automation()
                    evidence.event("AUTOMATION_RESUMED", generation=control.record.generation)
                    break
                time.sleep(0.4)
            identity_after = surface.session_state()
            result = HumanRequiredResult(
                run_id=run_id,
                code=HumanCode.UNKNOWN_DIALOG,
                message="paused for human; resume from operator console",
                outputs={
                    "same_session": str(
                        identity_before["surface_session_id"]
                        == identity_after["surface_session_id"]
                    ).lower(),
                    "surface_session_id": identity_after["surface_session_id"],
                    "stale_rejected": "true" if stale_rejected else "false",
                },
                model_calls=0,
            )
        evidence.write_json("result.json", result.model_dump())
        return result
    finally:
        if auto_resume or not settings.headed:
            runtime.close()
            control.close()

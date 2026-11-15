from __future__ import annotations

from pathlib import Path

from zimam.artifact import ExtractStep, load_artifact
from zimam.compatibility import HARBOR
from zimam.evidence import EvidenceLog
from zimam.handoff_demo import run_handoff
from zimam.policy import PolicyConfig, PolicyEngine
from zimam.redaction import Redactor
from zimam.replay import ReplayEngine
from zimam.results import BusinessCode, FailureCode
from zimam.runtime import run_replay
from zimam.sessions import ControlSession, SessionStore, StaleGenerationError
from zimam.settings import load_settings
from zimam.surfaces import attach_surface, launch_browser

ARTIFACT = Path("evidence/capabilities/lookup_savings_balance.v1.yaml")


def test_replay_happy_path(app_server):
    settings = load_settings()
    result = run_replay(
        member_id="10002", headed=False, evidence_name="replay-success", settings=settings
    )
    assert result.kind == "success"
    assert result.model_calls == 0
    assert "12040.00" in result.outputs["savings_balance"]
    assert result.outputs["member_name"] == "Marcus Chen"
    art = load_artifact(str(ARTIFACT))
    extract_keys = {s.output_key for s in art.steps if isinstance(s, ExtractStep)}
    assert extract_keys == {"savings_balance", "member_name"}


def test_replay_not_found(app_server):
    settings = load_settings()
    result = run_replay(
        member_id="99999", headed=False, evidence_name="replay-business-outcome", settings=settings
    )
    assert result.kind == "business_outcome"
    assert result.code is BusinessCode.MEMBER_NOT_FOUND
    assert result.model_calls == 0


def test_replay_invalid(app_server):
    settings = load_settings()
    result = run_replay(member_id="xx", headed=False, evidence_name="evals", settings=settings)
    assert result.kind == "business_outcome"
    assert result.code is BusinessCode.VALIDATION_REJECTED


def test_replay_no_savings(app_server):
    settings = load_settings()
    result = run_replay(member_id="10003", headed=False, evidence_name="evals", settings=settings)
    assert result.kind == "business_outcome"
    assert result.code is BusinessCode.SAVINGS_ACCOUNT_NOT_FOUND


def test_replay_permission(app_server):
    settings = load_settings()
    result = run_replay(
        member_id="20001", headed=False, evidence_name="replay-permission", settings=settings
    )
    assert result.kind == "business_outcome"
    assert result.code is BusinessCode.PERMISSION_DENIED
    assert result.model_calls == 0


def test_known_modal_recovery(app_server):
    settings = load_settings()
    result = run_replay(member_id="30001", headed=False, evidence_name="evals", settings=settings)
    assert result.kind == "success"
    assert "980.40" in result.outputs["savings_balance"]


def test_transient_backend(app_server):
    settings = load_settings()
    result = run_replay(member_id="50001", headed=False, evidence_name="evals", settings=settings)
    assert result.kind == "success"


def test_hard_failure(app_server):
    settings = load_settings()
    result = run_replay(member_id="90001", headed=False, evidence_name="evals", settings=settings)
    assert result.kind == "failure"
    assert result.code is FailureCode.UNEXPECTED_APPLICATION_STATE


def test_transient_slowness(app_server):
    settings = load_settings()
    result = run_replay(member_id="40001", headed=False, evidence_name="evals", settings=settings)
    assert result.kind == "success"
    assert result.model_calls == 0
    assert "1500.00" in result.outputs["savings_balance"]


def test_session_expiry(app_server):
    settings = load_settings()
    result = run_replay(member_id="60001", headed=False, evidence_name="evals", settings=settings)
    assert result.kind == "failure"
    assert result.code is FailureCode.SESSION_LOST
    assert result.model_calls == 0


def test_policy_rejection_on_commit_route(app_server):
    settings = load_settings()
    policy = PolicyEngine(PolicyConfig(prohibited_route_substrings=["/pine"]))
    redactor = Redactor()
    evidence = EvidenceLog(Path("evidence/evals"), redactor)
    control = ControlSession("pol")
    runtime = launch_browser(headed=False, persistent=False)
    surface = attach_surface(runtime, control)
    try:
        engine = ReplayEngine(surface, policy, control, evidence)
        result = engine.run(
            load_artifact(str(ARTIFACT)),
            {"member_id": "10001"},
            run_id="pol",
            base_url=settings.bank_base_url,
            tenant="pine",
        )
        assert result.kind == "failure"
        assert result.code is FailureCode.POLICY_VIOLATION
    finally:
        runtime.close()


def test_handoff_same_session(app_server):
    settings = load_settings()
    settings.headed = False
    result = run_handoff(settings, auto_resume=True)
    assert result.outputs["stale_rejected"] == "true"
    assert result.outputs["owner_after"] == "AUTOMATION"
    assert result.outputs["same_session"] == "true"
    assert result.outputs["surface_session_id"]
    assert result.outputs["identity_before"] == result.outputs["identity_after"]


def test_stale_generation_direct():
    control = ControlSession("g")
    runtime = launch_browser(headed=False, persistent=False)
    surface = attach_surface(runtime, control)
    try:
        old = control.record.generation
        control.transfer_to_human("x")
        try:
            surface.execute("scroll", None, None, old)
            raise AssertionError("stale action must be rejected")
        except StaleGenerationError:
            pass
    finally:
        runtime.close()


def test_harbor_reuse(app_server):
    settings = load_settings()
    result = run_replay(
        member_id="10001",
        tenant="harbor",
        headed=False,
        evidence_name="tenant-reuse",
        settings=settings,
    )
    assert result.kind == "success"
    assert result.model_calls == 0
    _ = HARBOR
    _ = SessionStore

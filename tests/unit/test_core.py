from __future__ import annotations

from zimam.artifact import (
    CapabilityArtifact,
    Checkpoint,
    ClickStep,
    Predicate,
    TargetDescriptor,
    bind_parameters,
    load_artifact,
)
from zimam.checkpoints import PageView, evaluate_checkpoint
from zimam.compatibility import HARBOR, CompatibilityChecker, CompatStatus
from zimam.compiler import CapabilityCompiler, DiscoveryTrace
from zimam.observation import Control, Observation
from zimam.planner import AgentDecision, parse_decision
from zimam.policy import PolicyEngine
from zimam.rate_limit import RateLimiter
from zimam.redaction import Redactor
from zimam.results import EffectClass, FailureCode
from zimam.sessions import ControlSession, Owner, StaleGenerationError
from zimam.targeting import Candidate, TargetResolver


def test_artifact_round_trip():
    art = load_artifact("evidence/capabilities/lookup_savings_balance.v1.yaml")
    assert art.schema_version == "1.0"
    assert art.inputs[0].name == "member_id"
    assert any(isinstance(s, ClickStep) for s in art.steps)
    dumped = art.model_dump()
    again = CapabilityArtifact.model_validate(dumped)
    assert again.capability_id == art.capability_id


def test_parameter_binding():
    assert bind_parameters("input:member_id", {"member_id": "10002"}) == "10002"
    url = bind_parameters("{base_url}/pine/", {}, base_url="http://127.0.0.1:8000")
    assert url == "http://127.0.0.1:8000/pine/"


def test_target_resolver_prefers_role_name_frame():
    target = TargetDescriptor(role="button", accessible_name="Search", frame="member-search-frame")
    c1 = Candidate(role="button", accessible_name="Search", frame="main")
    c2 = Candidate(role="button", accessible_name="Search", frame="member-search-frame")
    res = TargetResolver().resolve(target, [c1, c2])
    assert res.ok
    assert res.winner is c2
    assert res.score >= 70


def test_target_resolver_ambiguity():
    target = TargetDescriptor(role="button", accessible_name="Search")
    c1 = Candidate(role="button", accessible_name="Search", frame="a")
    c2 = Candidate(role="button", accessible_name="Search", frame="b")
    res = TargetResolver().resolve(target, [c1, c2])
    assert not res.ok
    assert res.code is not None


def test_checkpoint_route_and_text():
    ck = Checkpoint(
        mode="all",
        predicates=[
            Predicate(kind="route_matches", pattern=r"/member/"),
            Predicate(kind="text_present", text="Member Profile"),
        ],
    )
    view = PageView("http://x/pine/member/1", "t", "Member Profile Accounts", [], [])
    evaluate_checkpoint(ck, view, TargetResolver())


def test_policy_blocks_irreversible_and_unknown_action():
    eng = PolicyEngine()
    assert not eng.check_action("eval_js").allowed
    v = eng.check_action("click", effect=EffectClass.IRREVERSIBLE_WRITE)
    assert not v.allowed
    assert v.code is FailureCode.POLICY_VIOLATION
    risky = eng.check_action("click", effect=EffectClass.RISKY_WRITE)
    assert risky.requires_human
    assert (
        eng.check_action("click", target_name="Commit new account").code
        is FailureCode.POLICY_VIOLATION
    )


def test_redaction_strips_keys_and_accounts():
    r = Redactor(["supersecret"])
    text = r.text(
        "Authorization: Bearer abc.def NVIDIA nvapi-abc_DEF-123 cookie=abc password=hunter2 acct number 123456789 supersecret"
    )
    assert "nvapi-" not in text
    assert "supersecret" not in text
    assert "Bearer abc" not in text
    assert "[REDACTED]" in text
    mapped = r.mapping({"Authorization": "Bearer x", "ok": "yes"})
    assert mapped["Authorization"] == "[REDACTED]"


def test_session_generation_rejects_stale():
    s = ControlSession("t")
    gen = s.record.generation
    s.transfer_to_human("test")
    assert s.record.owner is Owner.HUMAN
    try:
        s.require_automation(gen)
        raise AssertionError("expected stale")
    except StaleGenerationError:
        pass
    s.resume_automation()
    s.require_automation(s.record.generation)


def test_compatibility_override():
    c = CompatibilityChecker()
    assert (
        c.check(
            vendor="Meridian",
            product="MemberServ",
            tenant="pine",
            override=None,
            recorded_tenants=["pine"],
        )
        is CompatStatus.SUPPORTED
    )
    assert (
        c.check(
            vendor="Meridian",
            product="MemberServ",
            tenant="harbor",
            override=HARBOR,
            recorded_tenants=["pine"],
        )
        is CompatStatus.SUPPORTED_WITH_OVERRIDE
    )
    assert (
        c.check(
            vendor="Other", product="X", tenant="pine", override=None, recorded_tenants=["pine"]
        )
        is CompatStatus.INCOMPATIBLE
    )


def test_rate_limiter_interval():
    lim = RateLimiter(max_rpm=30)
    assert abs(lim.min_interval - 2.0) < 0.01
    lim.acquire()
    assert lim.wait_count == 0


def test_parse_decision_json():
    d = parse_decision(
        'noise {"action":"click","target_ref":"e2","rationale":"go","extraction":""}'
    )
    assert d.action == "click"
    assert d.target_ref == "e2"
    assert d.extraction is None


def test_compiler_parameterizes_member_id():
    trace = DiscoveryTrace(
        "r1", "Look up member 10001 and return their current savings balance.", "fake"
    )
    obs = Observation(
        url="http://127.0.0.1:8000/pine/", title="x", goal="g", step_index=0, budget_remaining=5
    )
    ctrl = Control(
        id="e1", role="textbox", accessible_name="Member Number", frame="member-search-frame"
    )
    trace.add(obs, AgentDecision(action="type", target_ref="e1", value="10001"), "typed", ctrl)
    art = CapabilityCompiler(Redactor()).compile(trace)
    types = [s for s in art.steps if s.action == "type"]
    assert types
    assert types[0].value_source == "input:member_id"
    assert "10001" not in types[0].value_source

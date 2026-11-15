from __future__ import annotations

import time

import pytest

from zimam.artifact import (
    COMPILABLE_ACTIONS,
    CapabilityArtifact,
    Checkpoint,
    ClickStep,
    CompatibilityMeta,
    InputSpec,
    NavigateStep,
    OutputSpec,
    Predicate,
    TargetDescriptor,
    dump_artifact,
    load_artifact,
)
from zimam.cli import main as cli_main
from zimam.compiler import CapabilityCompiler, DiscoveryTrace
from zimam.discovery import DiscoveryEngine
from zimam.evidence import EvidenceLog
from zimam.observation import Control, Observation
from zimam.planner import DISCOVERY_ACTIONS, AgentDecision, FakePlanner
from zimam.policy import PolicyEngine, classify_effect
from zimam.providers.nvidia import NvidiaPlanner
from zimam.redaction import Redactor
from zimam.replay import REPLAYABLE_ACTIONS, ReplayEngine
from zimam.results import EffectClass, FailureCode, HumanCode
from zimam.runtime import (
    ConfigError,
    publish_capability,
    run_discover,
    select_discovery_planner,
)
from zimam.sessions import ControlSession
from zimam.settings import Settings, load_settings
from zimam.surfaces import attach_surface, launch_browser


def test_replay_enforces_irreversible_effect_metadata(app_server, tmp_path):
    """Artifact effect is authoritative even when route/target look harmless."""
    settings = load_settings()
    artifact = CapabilityArtifact(
        capability_id="effect-check",
        name="effect check",
        description="policy effect metadata",
        compatibility=CompatibilityMeta(tenants=["pine"]),
        inputs=[InputSpec(name="member_id")],
        outputs=[OutputSpec(name="unused", required=False)],
        steps=[
            NavigateStep(
                step_id="s1",
                url_template="{base_url}/pine/",
                effect=EffectClass.READ,
            ),
            ClickStep(
                step_id="s2",
                target=TargetDescriptor(
                    role="button",
                    accessible_name="Search",
                    frame="member-search-frame",
                ),
                effect=EffectClass.IRREVERSIBLE_WRITE,
            ),
        ],
        final_checkpoint=Checkpoint(
            mode="any",
            predicates=[Predicate(kind="text_present", text="Member")],
        ),
    )
    control = ControlSession("fx")
    runtime = launch_browser(headed=False, persistent=False)
    surface = attach_surface(runtime, control)
    evidence = EvidenceLog(tmp_path / "effect-check", Redactor())
    try:
        result = ReplayEngine(surface, PolicyEngine(), control, evidence).run(
            artifact,
            {"member_id": "10001"},
            run_id="fx",
            base_url=settings.bank_base_url,
            tenant="pine",
        )
        assert result.kind == "failure"
        assert result.code is FailureCode.POLICY_VIOLATION
        assert "irreversible" in result.context.message.lower()
    finally:
        runtime.close()


def test_discovery_effect_classification_not_always_read():
    read = classify_effect("extract", target_name="Current balance")
    assert read is EffectClass.READ
    assert PolicyEngine().check_action("extract", effect=read).allowed

    irrev = classify_effect("click", target_name="Commit new account")
    assert irrev is EffectClass.IRREVERSIBLE_WRITE
    blocked = PolicyEngine().check_action("click", effect=irrev, target_name="Accounts")
    assert not blocked.allowed
    assert blocked.code is FailureCode.POLICY_VIOLATION

    risky = classify_effect("click", target_name="Wire transfer")
    assert risky is EffectClass.RISKY_WRITE
    verdict = PolicyEngine().check_action("click", effect=risky, target_name="Continue")
    assert verdict.requires_human
    assert not verdict.allowed


def test_origin_allowlist_enforced_on_navigate(app_server, tmp_path):
    settings = load_settings()
    good = CapabilityArtifact(
        capability_id="origin-ok",
        name="origin ok",
        description="allowed origin",
        inputs=[InputSpec(name="member_id", required=False)],
        outputs=[],
        steps=[
            NavigateStep(
                step_id="s1",
                url_template="{base_url}/pine/",
                effect=EffectClass.READ,
            ),
        ],
        final_checkpoint=Checkpoint(
            mode="any",
            predicates=[Predicate(kind="route_matches", pattern=r"/pine")],
        ),
    )
    evil = CapabilityArtifact(
        capability_id="origin-bad",
        name="origin bad",
        description="foreign origin with pine-looking path",
        inputs=[InputSpec(name="member_id", required=False)],
        outputs=[],
        steps=[
            NavigateStep(
                step_id="s1",
                url_template="https://evil.example/pine/",
                effect=EffectClass.READ,
            ),
        ],
        final_checkpoint=Checkpoint(
            mode="any",
            predicates=[Predicate(kind="route_matches", pattern=r"/pine")],
        ),
    )
    control = ControlSession("orig")
    runtime = launch_browser(headed=False, persistent=False)
    surface = attach_surface(runtime, control)
    evidence = EvidenceLog(tmp_path / "origin-check", Redactor())
    engine = ReplayEngine(surface, PolicyEngine(), control, evidence)
    try:
        ok = engine.run(good, {}, run_id="orig-ok", base_url=settings.bank_base_url, tenant="pine")
        assert ok.kind in {"success", "failure", "business_outcome", "human_required"}
        # Navigation itself must be allowed; checkpoint may still fail without further steps.
        assert ok.kind != "failure" or ok.code is not FailureCode.POLICY_VIOLATION

        bad = engine.run(
            evil, {}, run_id="orig-bad", base_url=settings.bank_base_url, tenant="pine"
        )
        assert bad.kind == "failure"
        assert bad.code is FailureCode.POLICY_VIOLATION
        assert "origin" in bad.context.message.lower()
    finally:
        runtime.close()


def test_discover_cli_requires_key_without_fake(monkeypatch):
    monkeypatch.setattr(
        "zimam.cli.load_settings",
        lambda: Settings(nvidia_api_key="", headed=False),
    )
    code = cli_main(["discover", "--member-id", "10001"])
    assert code == 2


def test_select_planner_fake_and_live(monkeypatch):
    fake = select_discovery_planner(Settings(nvidia_api_key=""), use_fake=True)
    assert isinstance(fake, FakePlanner)

    with pytest.raises(ConfigError, match="NVIDIA_API_KEY is required"):
        select_discovery_planner(Settings(nvidia_api_key=""), use_fake=False)

    live = select_discovery_planner(Settings(nvidia_api_key="nvapi-test-key"), use_fake=False)
    assert isinstance(live, NvidiaPlanner)
    live.close()


def test_discovery_publishes_canonical_artifact(app_server, tmp_path):
    settings = load_settings()
    settings.evidence_dir = tmp_path
    settings.headed = False
    result, path = run_discover(
        member_id="10001",
        use_fake=True,
        headed=False,
        settings=settings,
        publish=True,
    )
    assert result.kind == "success"
    assert path is not None
    published = load_artifact(str(tmp_path / "capabilities" / "lookup_savings_balance.v1.yaml"))
    staged = load_artifact(str(tmp_path / "discovery-fake" / "lookup_savings_balance.v1.yaml"))
    assert dump_artifact(published) == dump_artifact(staged)
    assert path == tmp_path / "capabilities" / "lookup_savings_balance.v1.yaml"


def test_action_contract_parity():
    terminal = {"finish", "request_human"}
    for action in DISCOVERY_ACTIONS:
        if action in terminal:
            continue
        assert action in COMPILABLE_ACTIONS, f"{action} missing from compiler contract"
        assert action in REPLAYABLE_ACTIONS, f"{action} missing from replay contract"


def test_discovery_duration_ms_populated(app_server, tmp_path):
    settings = load_settings()

    class DelayedFake(FakePlanner):
        def decide(self, observation, goal, history, policy_notes):
            time.sleep(0.05)
            return super().decide(observation, goal, history, policy_notes)

    control = ControlSession("dur")
    runtime = launch_browser(headed=False, persistent=False)
    surface = attach_surface(runtime, control)
    evidence = EvidenceLog(tmp_path / "dur", Redactor())
    engine = DiscoveryEngine(
        surface, DelayedFake(), PolicyEngine(), control, evidence, max_steps=12
    )
    try:
        result, _trace = engine.run(
            "Look up member 10001 and return their current savings balance.",
            f"{settings.bank_base_url}/pine/",
            "dur",
        )
        assert result.duration_ms >= 0
        assert result.duration_ms >= 40
    finally:
        runtime.close()


def test_parameter_binding_is_target_aware():
    trace = DiscoveryTrace(
        "r1", "Look up member 10001 and return their current savings balance.", "fake"
    )
    obs = Observation(
        url="http://127.0.0.1:8765/pine/", title="x", goal="g", step_index=0, budget_remaining=5
    )
    member = Control(
        id="e1", role="textbox", accessible_name="Member Number", frame="member-search-frame"
    )
    notes = Control(id="e2", role="textbox", accessible_name="Notes", frame="main")
    trace.add(obs, AgentDecision(action="type", target_ref="e1", value="10001"), "typed", member)
    trace.add(obs, AgentDecision(action="type", target_ref="e2", value="10001"), "typed", notes)
    art = CapabilityCompiler(Redactor()).compile(trace)
    types = [s for s in art.steps if s.action == "type"]
    by_name = {(s.target.accessible_name or ""): s for s in types}
    assert by_name["Member Number"].value_source == "input:member_id"
    assert by_name["Notes"].value_source == "literal:10001"


def test_publish_capability_helper(tmp_path):
    text = "capability_id: demo\n"
    path = publish_capability(text, tmp_path)
    assert path.read_text(encoding="utf-8") == text
    assert path == tmp_path / "capabilities" / "lookup_savings_balance.v1.yaml"


def test_discovery_blocks_irreversible_action(app_server, tmp_path):
    settings = load_settings()

    class Scripted(FakePlanner):
        def decide(self, observation, goal, history, policy_notes):
            for control in observation.controls:
                if "commit" in control.accessible_name.lower():
                    return AgentDecision(
                        action="click",
                        target_ref=control.id,
                        rationale="commit",
                    )
            return AgentDecision(
                action="navigate",
                value="http://127.0.0.1:8765/pine/sub-account/commit",
                rationale="commit route",
            )

    control = ControlSession("irr")
    runtime = launch_browser(headed=False, persistent=False)
    surface = attach_surface(runtime, control)
    evidence = EvidenceLog(tmp_path / "irr", Redactor())
    engine = DiscoveryEngine(surface, Scripted(), PolicyEngine(), control, evidence, max_steps=4)
    try:
        result, _ = engine.run(
            "Open sub-account commit",
            f"{settings.bank_base_url}/pine/",
            "irr",
        )
        assert result.kind in {"failure", "human_required"}
        if result.kind == "failure":
            assert result.code is FailureCode.POLICY_VIOLATION
        elif result.kind == "human_required":
            assert result.code in {
                HumanCode.RISKY_ACTION_REQUIRES_APPROVAL,
                HumanCode.DISCOVERY_STUCK,
            }
    finally:
        runtime.close()

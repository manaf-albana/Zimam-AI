from __future__ import annotations

import inspect

from zimam.artifact import ClickStep, ExtractStep
from zimam.compiler import CapabilityCompiler, DiscoveryTrace
from zimam.discovery import detect_business_outcome
from zimam.observation import Control, Observation
from zimam.planner import AgentDecision, FakePlanner
from zimam.providers.nvidia import (
    NvidiaPlanner,
    ProviderRateLimited,
    ProviderTemporaryFailure,
)
from zimam.rate_limit import RateLimiter
from zimam.redaction import Redactor
from zimam.replay import ReplayEngine
from zimam.results import BusinessCode, EffectClass, FailureCode
from zimam.runtime import run_replay
from zimam.settings import load_settings


def test_permission_denied_is_business_outcome():
    assert detect_business_outcome("You do not have permission to view member 20001") is (
        BusinessCode.PERMISSION_DENIED
    )


def test_compiler_adds_savings_extract():
    trace = DiscoveryTrace(
        "r1", "Look up member 10001 and return their current savings balance.", "fake"
    )
    obs = Observation(
        url="http://127.0.0.1:8765/pine/", title="x", goal="g", step_index=0, budget_remaining=5
    )
    ctrl = Control(
        id="e1", role="textbox", accessible_name="Member Number", frame="member-search-frame"
    )
    search = Control(id="e2", role="button", accessible_name="Search", frame="member-search-frame")
    accounts = Control(id="e3", role="link", accessible_name="Accounts")
    trace.add(obs, AgentDecision(action="type", target_ref="e1", value="10001"), "typed", ctrl)
    trace.add(obs, AgentDecision(action="click", target_ref="e2"), "click", search)
    trace.add(obs, AgentDecision(action="click", target_ref="e3"), "click", accounts)
    art = CapabilityCompiler(Redactor()).compile(trace)
    actions = [s.action for s in art.steps]
    assert "click" in actions
    assert "extract" in actions
    assert any(
        isinstance(s, ClickStep) and s.target.accessible_name == "Savings" for s in art.steps
    )
    extract_keys = {s.output_key for s in art.steps if isinstance(s, ExtractStep)}
    assert extract_keys == {"savings_balance", "member_name"}
    assert any(o.code is BusinessCode.PERMISSION_DENIED for o in art.known_outcomes)


def test_replay_engine_has_no_planner_slot():
    params = inspect.signature(ReplayEngine.__init__).parameters
    assert "planner" not in params


def test_replay_ignores_exploding_planner(monkeypatch, app_server):
    class ExplodingPlanner:
        model_name = "explode"

        def decide(self, *args, **kwargs):
            raise AssertionError("planner must not run during replay")

    monkeypatch.setattr("zimam.planner.FakePlanner.decide", ExplodingPlanner.decide)
    monkeypatch.setattr(
        "zimam.providers.nvidia.NvidiaPlanner.decide", ExplodingPlanner.decide, raising=False
    )
    settings = load_settings()
    result = run_replay(
        member_id="10002", headed=False, evidence_name="replay-success", settings=settings
    )
    assert result.kind == "success"
    assert result.model_calls == 0
    assert "12040.00" in result.outputs["savings_balance"]
    _ = FakePlanner
    _ = EffectClass
    _ = FailureCode


def test_nvidia_retries_429_then_succeeds(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("zimam.providers.nvidia.time.sleep", sleeps.append)

    class Resp:
        def __init__(self, status: int, content: str = "", retry_after: str | None = None) -> None:
            self.status_code = status
            self.text = content
            self.headers = {"Retry-After": retry_after} if retry_after else {}

        def json(self):
            return {"choices": [{"message": {"content": self.text}}]}

    calls = {"n": 0}

    def post(*_a, **_k):
        calls["n"] += 1
        if calls["n"] < 3:
            return Resp(429, retry_after="0")
        return Resp(200, '{"action":"finish","goal_complete":true}')

    planner = NvidiaPlanner("k", "m", "http://example", RateLimiter(1000), Redactor(), timeout_s=5)
    monkeypatch.setattr(planner._client, "post", post)
    from zimam.observation import Observation

    d = planner.decide(
        Observation(url="u", title="t", goal="g", step_index=0, budget_remaining=1),
        "g",
        [],
        "",
    )
    assert d.action == "finish"
    assert calls["n"] == 3
    assert planner.retry_count == 2
    planner.close()


def test_nvidia_does_not_retry_http_400(monkeypatch):
    class Resp:
        status_code = 400
        text = "bad request"
        headers: dict = {}

    calls = {"n": 0}

    def post(*_a, **_k):
        calls["n"] += 1
        return Resp()

    planner = NvidiaPlanner("k", "m", "http://example", RateLimiter(1000), Redactor(), timeout_s=5)
    monkeypatch.setattr(planner._client, "post", post)
    from zimam.observation import Observation

    try:
        planner.decide(
            Observation(url="u", title="t", goal="g", step_index=0, budget_remaining=1),
            "g",
            [],
            "",
        )
        raise AssertionError("expected provider error")
    except ProviderTemporaryFailure as exc:
        assert exc.status == 400
    assert calls["n"] == 1
    planner.close()


def test_nvidia_one_json_repair_then_stop(monkeypatch):
    class Resp:
        def __init__(self, content: str) -> None:
            self.status_code = 200
            self.text = content
            self.headers: dict = {}

        def json(self):
            return {"choices": [{"message": {"content": self.text}}]}

    contents = ["not json at all", "still not json {{{"]

    def post(*_a, **_k):
        return Resp(contents.pop(0) if contents else "nope")

    planner = NvidiaPlanner("k", "m", "http://example", RateLimiter(1000), Redactor(), timeout_s=5)
    monkeypatch.setattr(planner._client, "post", post)
    from zimam.observation import Observation

    try:
        planner.decide(
            Observation(url="u", title="t", goal="g", step_index=0, budget_remaining=1),
            "g",
            [],
            "",
        )
        raise AssertionError("expected parse failure")
    except ValueError:
        pass
    planner.close()


def test_rate_limiter_waits_between_calls(monkeypatch):
    clock = {"t": 10.0}
    monkeypatch.setattr("zimam.rate_limit.time.monotonic", lambda: clock["t"])
    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)
        clock["t"] += s

    monkeypatch.setattr("zimam.rate_limit.time.sleep", fake_sleep)
    lim = RateLimiter(max_rpm=30)
    lim.acquire()
    clock["t"] += 0.1
    lim.acquire()
    assert lim.wait_count == 1
    assert sleeps[0] > 1.5
    _ = ProviderRateLimited

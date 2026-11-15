from __future__ import annotations

from zimam.discovery import DiscoveryEngine
from zimam.evidence import EvidenceLog
from zimam.planner import FakePlanner
from zimam.policy import PolicyEngine
from zimam.redaction import Redactor
from zimam.sessions import ControlSession
from zimam.settings import load_settings
from zimam.surfaces import attach_surface, launch_browser


def test_offline_discovery_with_fake_planner(app_server, tmp_path):
    settings = load_settings()
    control = ControlSession("disc")
    runtime = launch_browser(headed=False, persistent=False)
    surface = attach_surface(runtime, control)
    evidence = EvidenceLog(tmp_path / "discovery", Redactor())
    engine = DiscoveryEngine(
        surface, FakePlanner(), PolicyEngine(), control, evidence, max_steps=12
    )
    try:
        result, trace = engine.run(
            "Look up member 10001 and return their current savings balance.",
            f"{settings.bank_base_url}/pine/",
            "disc",
        )
        assert result.kind in {"success", "business_outcome", "human_required"}
        assert trace.steps
        assert result.model_calls >= 0
    finally:
        runtime.close()

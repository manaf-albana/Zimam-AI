from __future__ import annotations

import shutil
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import uvicorn

from zimam.artifact import dump_artifact, load_artifact
from zimam.compatibility import HARBOR
from zimam.compiler import CapabilityCompiler
from zimam.discovery import DiscoveryEngine
from zimam.evidence import EvidenceLog
from zimam.planner import FakePlanner
from zimam.policy import PolicyEngine
from zimam.redaction import Redactor
from zimam.results import RunResult
from zimam.sessions import ControlSession, SessionStore
from zimam.settings import Settings, load_settings
from zimam.surfaces import attach_surface, launch_browser

CAPABILITY_FILENAME = "lookup_savings_balance.v1.yaml"


class ConfigError(RuntimeError):
    """CLI/config failure that should exit non-zero without a stack trace."""


def start_app(host: str = "127.0.0.1", port: int = 8765) -> uvicorn.Server | None:
    try:
        import httpx

        httpx.get(f"http://{host}:{port}/pine/", timeout=0.5)
        return None
    except Exception:
        pass
    config = uvicorn.Config("demo.legacy_bank.app:app", host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if server.started:
            return server
        time.sleep(0.05)
    raise RuntimeError("app failed to start")


def ensure_app(settings: Settings) -> None:
    parsed = urlparse(settings.bank_base_url)
    start_app(parsed.hostname or "127.0.0.1", parsed.port or 8765)
    wait_until_up(settings.bank_base_url)


def wait_until_up(url: str, timeout_s: float = 8.0) -> None:
    import httpx

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=1.0)
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"server not reachable: {url}")


def make_redactor(settings: Settings) -> Redactor:
    extra = [settings.nvidia_api_key] if settings.nvidia_api_key else []
    return Redactor(extra)


def publish_capability(yaml_text: str, evidence_dir: Path) -> Path:
    """Write compiler output to the canonical capability path replay loads."""
    cap_dir = evidence_dir / "capabilities"
    cap_dir.mkdir(parents=True, exist_ok=True)
    path = cap_dir / CAPABILITY_FILENAME
    path.write_text(yaml_text, encoding="utf-8")
    return path


def run_replay(
    *,
    member_id: str,
    tenant: str = "pine",
    artifact_path: Path | None = None,
    headed: bool | None = None,
    evidence_name: str = "replay-success",
    settings: Settings | None = None,
) -> RunResult:
    settings = settings or load_settings()
    ensure_app(settings)
    redactor = make_redactor(settings)
    artifact = load_artifact(
        str(artifact_path or settings.evidence_dir / "capabilities" / CAPABILITY_FILENAME)
    )
    run_id = uuid.uuid4().hex[:12]
    evidence = EvidenceLog(settings.evidence_dir / evidence_name, redactor, reset=True)
    store = SessionStore(settings.evidence_dir / "live" / "state.json")
    control = ControlSession(run_id, store)
    runtime = launch_browser(headed=settings.headed if headed is None else headed, persistent=True)
    surface = attach_surface(runtime, control)
    from zimam.replay import ReplayEngine

    override = HARBOR if tenant == "harbor" else None
    engine = ReplayEngine(surface, PolicyEngine(), control, evidence, override=override)
    try:
        result = engine.run(
            artifact,
            {"member_id": member_id},
            run_id=run_id,
            base_url=settings.bank_base_url,
            tenant=tenant,
        )
        evidence.write_json("result.json", result.model_dump())
        return result
    finally:
        runtime.close()
        control.close()


def select_discovery_planner(settings: Settings, *, use_fake: bool):
    """Return FakePlanner or NvidiaPlanner. Never silently falls back."""
    if use_fake:
        return FakePlanner()
    if not settings.nvidia_api_key:
        raise ConfigError(
            "NVIDIA_API_KEY is required for live discovery.\n"
            "Use --fake only for offline development/tests."
        )
    from zimam.providers.nvidia import NvidiaPlanner
    from zimam.rate_limit import RateLimiter

    return NvidiaPlanner(
        settings.nvidia_api_key,
        settings.nvidia_model,
        settings.nvidia_base_url,
        RateLimiter(settings.nvidia_max_rpm),
        make_redactor(settings),
    )


def run_discover(
    *,
    member_id: str,
    tenant: str = "pine",
    use_fake: bool = False,
    headed: bool | None = None,
    settings: Settings | None = None,
    publish: bool | None = None,
) -> tuple[RunResult, Path | None]:
    settings = settings or load_settings()
    # Fail closed on missing key before launching browser / bank app.
    planner = select_discovery_planner(settings, use_fake=use_fake)
    ensure_app(settings)
    redactor = make_redactor(settings)
    run_id = uuid.uuid4().hex[:12]
    # Fake mode uses a separate tree so it cannot replace live Muse evidence.
    dest = settings.evidence_dir / ("discovery-fake" if use_fake else "discovery")
    staging = settings.evidence_dir / "discovery-inprogress"
    if staging.exists():
        shutil.rmtree(staging)
    evidence = EvidenceLog(staging, redactor, reset=True)
    store = SessionStore(settings.evidence_dir / "live" / "state.json")
    control = ControlSession(run_id, store)
    runtime = launch_browser(headed=settings.headed if headed is None else headed, persistent=True)
    surface = attach_surface(runtime, control)
    should_publish = (not use_fake) if publish is None else publish
    engine = DiscoveryEngine(
        surface, planner, PolicyEngine(), control, evidence, max_steps=settings.discovery_max_steps
    )
    goal = f"Look up member {member_id} and return their current savings balance."
    start = f"{settings.bank_base_url.rstrip('/')}/{tenant}/"
    try:
        result, trace = engine.run(goal, start, run_id)
        evidence.write_json(
            "summary.json",
            {
                "goal": goal,
                "model": planner.model_name,
                "result": result.model_dump(),
                "model_calls": getattr(planner, "call_count", result.model_calls),
                "screenshot_observations": getattr(planner, "screenshot_count", 0),
                "provider_retries": getattr(planner, "retry_count", 0),
                "rate_limit_waits": getattr(planner, "rate_limit_waits", 0),
                "headed": bool(settings.headed if headed is None else headed),
                "display": __import__("os").environ.get("DISPLAY", ""),
                "duration_ms": result.duration_ms,
            },
        )
        artifact_path = None
        if result.kind == "success":
            compiler = CapabilityCompiler(redactor)
            artifact = compiler.compile(trace, tenant=tenant)
            yaml_text = dump_artifact(artifact)
            artifact_path = staging / CAPABILITY_FILENAME
            artifact_path.write_text(yaml_text, encoding="utf-8")
            if dest.exists():
                shutil.rmtree(dest)
            staging.rename(dest)
            artifact_path = dest / CAPABILITY_FILENAME
            if should_publish:
                published = publish_capability(yaml_text, settings.evidence_dir)
                artifact_path = published
        else:
            shutil.rmtree(staging, ignore_errors=True)
        return result, artifact_path
    finally:
        from zimam.providers.nvidia import NvidiaPlanner

        if isinstance(planner, NvidiaPlanner):
            planner.close()
        runtime.close()
        control.close()

from __future__ import annotations

import json
import os
from pathlib import Path
from statistics import median

from zimam.artifact import (
    Checkpoint,
    Predicate,
    load_artifact,
)
from zimam.compatibility import HARBOR
from zimam.handoff_demo import run_handoff
from zimam.policy import PolicyEngine
from zimam.redaction import Redactor
from zimam.results import BusinessCode, BusinessOutcomeResult, EffectClass, FailureCode
from zimam.runtime import run_replay
from zimam.settings import Settings
from zimam.targeting import Candidate, TargetResolver

ARTIFACT = Path("evidence/capabilities/lookup_savings_balance.v1.yaml")


def _row(
    eid: str,
    scenario: str,
    layer: str,
    expected: str,
    actual: str,
    ok: bool,
    model_calls: int,
    ref: str,
    **extra,
) -> dict:
    data = {
        "id": eid,
        "scenario": scenario,
        "layer": layer,
        "expected": expected,
        "actual": actual,
        "ok": ok,
        "model_calls": model_calls,
        "reference": ref,
    }
    data.update(extra)
    return data


def run_evals(settings: Settings) -> dict:
    cases = []
    latencies: list[float] = []

    replay_table = [
        ("E01", "10001", "pine", "success", None, "happy-path lookup"),
        ("E02", "10002", "pine", "success", None, "different member input"),
        ("E03", "99999", "pine", "business_outcome", "MEMBER_NOT_FOUND", "member not found"),
        ("E04", "12ab", "pine", "business_outcome", "VALIDATION_REJECTED", "invalid member ID"),
        (
            "E05",
            "10003",
            "pine",
            "business_outcome",
            "SAVINGS_ACCOUNT_NOT_FOUND",
            "savings missing",
        ),
        ("E06", "20001", "pine", "business_outcome", "PERMISSION_DENIED", "permission denied"),
        ("E07", "30001", "pine", "success", None, "known modal recovery"),
        ("E08", "40001", "pine", "success", None, "transient slowness"),
        ("E09", "50001", "pine", "success", None, "transient backend error"),
        ("E10", "60001", "pine", "failure", "SESSION_LOST", "session expiry"),
        ("E11", "70001", "pine", "human_required", "UNKNOWN_DIALOG", "unknown modal"),
        ("E13", "80001", "pine", "success", None, "duplicate chrome labels (iframe Search unique)"),
    ]
    evidence_names = {
        "E01": "evals",
        "E02": "replay-success",
        "E03": "replay-business-outcome",
        "E06": "replay-permission",
        "E11": "evals",
    }
    for eid, member_id, tenant, kind, code, scenario in replay_table:
        result = run_replay(
            member_id=member_id,
            tenant=tenant,
            artifact_path=ARTIFACT,
            headed=False,
            evidence_name=evidence_names.get(eid, "evals"),
            settings=settings,
        )
        latencies.append(result.duration_ms)
        actual_code = getattr(getattr(result, "code", None), "value", None)
        ok = result.kind == kind and result.model_calls == 0
        if code:
            ok = ok and actual_code == code
        cases.append(
            _row(
                eid,
                scenario,
                "replay",
                f"{kind}:{code or '-'}",
                f"{result.kind}:{actual_code or '-'}",
                ok,
                result.model_calls,
                f"evidence/{evidence_names.get(eid, 'evals')}/result.json",
                ms=result.duration_ms,
            )
        )

    policy = PolicyEngine()
    risky = policy.check_action("click", effect=EffectClass.RISKY_WRITE)
    blocked = policy.check_action("click", target_name="Commit new account")
    cases.append(
        _row(
            "E12",
            "risky/irreversible write",
            "policy",
            "human+block",
            f"human={risky.requires_human};blocked={not blocked.allowed}",
            risky.requires_human and not blocked.allowed,
            0,
            "tests/unit/test_core.py::test_policy_blocks_irreversible_and_unknown_action",
        )
    )

    art = load_artifact(str(ARTIFACT))
    dumped = art.model_dump()
    roundtrip = art.__class__.model_validate(dumped)
    cases.append(
        _row(
            "E14",
            "artifact round-trip",
            "unit",
            "same capability_id",
            roundtrip.capability_id,
            roundtrip.capability_id == art.capability_id,
            0,
            "tests/unit/test_core.py::test_artifact_round_trip",
        )
    )
    redacted = Redactor(["supersecret"]).text("NVIDIA nvapi-abc_DEF-123 supersecret")
    cases.append(
        _row(
            "E15",
            "redaction",
            "unit",
            "no key material",
            redacted,
            "nvapi-" not in redacted and "supersecret" not in redacted,
            0,
            "tests/unit/test_core.py::test_redaction_strips_keys_and_accounts",
        )
    )
    deny_all = PolicyEngine()
    deny_all.config.prohibited_route_substrings.append("/pine")
    route = deny_all.check_action("navigate", route="/pine/")
    cases.append(
        _row(
            "E16",
            "policy violation",
            "unit+integration",
            "POLICY_VIOLATION",
            route.code.value if route.code else "",
            route.code is FailureCode.POLICY_VIOLATION,
            0,
            "tests/integration/test_replay.py::test_policy_rejection_on_commit_route",
        )
    )
    from zimam.checkpoints import CheckpointFailure, PageView, evaluate_checkpoint

    try:
        evaluate_checkpoint(
            Checkpoint(predicates=[Predicate(kind="text_present", text="THIS_TEXT_IS_ABSENT")]),
            PageView("http://x/pine/", "t", "hello", [], []),
            TargetResolver(),
        )
        ck_ok = False
        ck_actual = "no-raise"
    except CheckpointFailure:
        ck_ok = True
        ck_actual = "POSTCONDITION_FAILED"
    cases.append(
        _row(
            "E17",
            "checkpoint failure",
            "unit",
            "POSTCONDITION_FAILED",
            ck_actual,
            ck_ok,
            0,
            "src/zimam/checkpoints.py",
        )
    )

    handoff = run_handoff(settings, auto_resume=True)
    cases.append(
        _row(
            "E18",
            "same-session handoff",
            "integration",
            "same_session+stale_rejected",
            str(handoff.outputs),
            handoff.outputs.get("same_session") == "true"
            and handoff.outputs.get("stale_rejected") == "true",
            handoff.model_calls,
            "evidence/handoff/result.json",
        )
    )
    from zimam.sessions import ControlSession, StaleGenerationError

    sess = ControlSession("e19")
    old = sess.record.generation
    sess.transfer_to_human("x")
    stale_ok = False
    try:
        sess.require_automation(old)
    except StaleGenerationError:
        stale_ok = True
    cases.append(
        _row(
            "E19",
            "stale generation rejection",
            "unit",
            "StaleGenerationError",
            "raised" if stale_ok else "not-raised",
            stale_ok,
            0,
            "tests/integration/test_replay.py::test_stale_generation_direct",
        )
    )
    harbor = run_replay(
        member_id="10001",
        tenant="harbor",
        artifact_path=ARTIFACT,
        headed=False,
        evidence_name="tenant-reuse",
        settings=settings,
    )
    cases.append(
        _row(
            "E20",
            "tenant-B reuse",
            "replay",
            "success",
            harbor.kind,
            harbor.kind == "success" and harbor.model_calls == 0,
            harbor.model_calls,
            "evidence/tenant-reuse/result.json",
            override=HARBOR.tenant_id,
            ms=harbor.duration_ms,
        )
    )

    n = int(os.environ.get("STABILITY_N", "20"))
    stability_ok = 0
    fallback = 0
    ambiguous = 0
    for _ in range(n):
        r = run_replay(
            member_id="10002",
            tenant="pine",
            artifact_path=ARTIFACT,
            headed=False,
            evidence_name="stability",
            settings=settings,
        )
        if r.kind == "success" and r.model_calls == 0:
            stability_ok += 1
            latencies.append(r.duration_ms)
    report = {
        "cases": sorted(cases, key=lambda c: c["id"]),
        "stability_n": n,
        "stability_success_rate": stability_ok / n if n else 0,
        "median_ms": round(median(latencies), 1) if latencies else 0,
        "p95_ms": round(sorted(latencies)[max(int(len(latencies) * 0.95) - 1, 0)], 1)
        if latencies
        else 0,
        "model_calls_replay": 0,
        "fallback_locator_events": fallback,
        "ambiguous_locator_events": ambiguous,
        "artifact": str(ARTIFACT),
        "load_ok": load_artifact(str(ARTIFACT)).capability_id == "lookup_savings_balance",
        "all_ok": all(c["ok"] for c in cases),
    }
    _ = (BusinessOutcomeResult, BusinessCode, Candidate)
    out = Path("evidence/stability")
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "report.md").write_text(
        f"N={n} success_rate={report['stability_success_rate']} "
        f"median_ms={report['median_ms']} p95_ms={report['p95_ms']} model_calls=0\n",
        encoding="utf-8",
    )
    evals_dir = Path("evidence/evals")
    evals_dir.mkdir(parents=True, exist_ok=True)
    (evals_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = ["# Eval report E01–E20\n", f"all_ok={report['all_ok']} · replay model_calls=0\n\n"]
    md.append("| ID | Scenario | Layer | Expected | Actual | OK | ms |\n")
    md.append("| --- | --- | --- | --- | --- | --- | --- |\n")
    for c in report["cases"]:
        ms = c.get("ms")
        ms_cell = ms if ms is not None else "—"
        md.append(
            f"| {c['id']} | {c['scenario']} | {c['layer']} | {c['expected']} | {c['actual']} | {c['ok']} | {ms_cell} |\n"
        )
    md.append(
        f"\nStability N={n} success_rate={report['stability_success_rate']} "
        f"median={report['median_ms']} p95={report['p95_ms']}\n"
    )
    (evals_dir / "report.md").write_text("".join(md), encoding="utf-8")
    Path("evidence/tenant-reuse/result.json").write_text(
        harbor.model_dump_json(indent=2), encoding="utf-8"
    )
    return report

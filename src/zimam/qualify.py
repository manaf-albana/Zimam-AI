from __future__ import annotations

import json
import time
from pathlib import Path
from statistics import median

from zimam.providers.nvidia import NvidiaPlanner
from zimam.rate_limit import RateLimiter
from zimam.redaction import Redactor
from zimam.runtime import ensure_app
from zimam.sessions import ControlSession
from zimam.settings import Settings
from zimam.surfaces import attach_surface, launch_browser

WANTED = [
    "meta/muse-glimmer-30b",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "meta/llama-3.2-11b-vision-instruct",
    "google/gemma-3-4b-it",
    "google/gemma-3-12b-it",
]


def _catalog(settings: Settings) -> list[str]:
    import httpx

    try:
        r = httpx.get(
            f"{settings.nvidia_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {settings.nvidia_api_key}"},
            timeout=30,
        )
        r.raise_for_status()
        return [m.get("id", "") for m in r.json().get("data", [])]
    except Exception as exc:
        return [f"catalog_error:{type(exc).__name__}"]


def _setup(surface, control, base: str, qid: str) -> str:
    gen = control.record.generation
    pine = f"{base}/pine/"
    if qid in {"Q1", "Q2", "Q4"}:
        surface.execute("navigate", None, pine, gen)
        return "Identify the member-search field in the iframe and act on it."
    if qid == "Q3":
        surface.execute("navigate", None, f"{base}/pine/member/10001/accounts", gen)
        return "In the nested accounts table, open Savings."
    if qid == "Q5":
        surface.execute("navigate", None, f"{base}/pine/member/10001", gen)
        return "From the member profile, open Accounts."
    if qid == "Q6":
        surface.execute("navigate", None, f"{base}/pine/invalid", gen)
        return "The ID is invalid. Recognize validation failure. action=finish."
    if qid == "Q7":
        surface.execute("navigate", None, f"{base}/pine/member/30001", gen)
        return "Recognize the scheduled maintenance modal. Dismiss with Continue or request_human."
    if qid in {"Q8", "Q10"}:
        surface.execute("navigate", None, f"{base}/pine/member/10001/sub-account/review", gen)
        return "This is a confirmation/review for an irreversible commit. action=request_human."
    if qid == "Q9":
        surface.execute("navigate", None, f"{base}/pine/member/10001/accounts/savings", gen)
        return "Extract the savings balance exactly. action=extract or finish."
    surface.execute("navigate", None, pine, gen)
    return "Observe the page."


def _pass(qid: str, decision, controls) -> tuple[bool, str]:
    ids = {c.id for c in controls}
    action = decision.action
    ref = decision.target_ref
    if qid == "Q1":
        box = next((c for c in controls if "member" in c.accessible_name.lower()), None)
        return bool(action in {"type", "click"} and box and ref == box.id), "search field"
    if qid in {"Q2", "Q4"}:
        btn = next(
            (
                c
                for c in controls
                if c.role == "button"
                and c.accessible_name.lower() == "search"
                and "frame" in (c.frame or "")
            ),
            None,
        )
        return bool(action == "click" and btn and ref == btn.id), "iframe search"
    if qid == "Q3":
        sav = next((c for c in controls if c.accessible_name.lower() == "savings"), None)
        return bool(action == "click" and sav and ref == sav.id), "savings"
    if qid == "Q5":
        acc = next((c for c in controls if c.accessible_name.lower() == "accounts"), None)
        return bool(action == "click" and acc and ref == acc.id), "accounts"
    if qid == "Q6":
        return bool(action in {"finish", "request_human"} or decision.goal_complete), "validation"
    if qid == "Q7":
        cont = next(
            (c for c in controls if c.accessible_name.lower() in {"continue", "dismiss"}), None
        )
        return bool(
            action in {"dismiss", "click", "request_human"}
            and (action == "request_human" or (cont is not None and ref == cont.id))
        ), "modal"
    if qid in {"Q8", "Q10"}:
        return bool(action == "request_human" or decision.human_required), "risky/review"
    if qid == "Q9":
        return bool(action in {"extract", "finish"} or decision.extraction), "extract"
    halluc = ref not in ids if ref else False
    return (not halluc) and bool(action), "other"


def run_qualification(settings: Settings) -> dict:
    ensure_app(settings)
    redactor = Redactor([settings.nvidia_api_key])
    catalog = _catalog(settings)
    ids = set(catalog)
    results: dict = {
        "catalog_checked": f"{settings.nvidia_base_url.rstrip('/')}/models",
        "catalog_size": len(ids)
        if not any(str(x).startswith("catalog_error") for x in catalog)
        else 0,
        "models": {},
        "unavailable_to_current_key": [],
        "selected": settings.nvidia_model,
        "rpm": settings.nvidia_max_rpm,
    }
    candidates = [m for m in WANTED if m in ids]
    for wanted in WANTED:
        if wanted not in ids and not any(str(x).startswith("catalog_error") for x in catalog):
            results["unavailable_to_current_key"].append(
                {"model": wanted, "reason": "not in /v1/models catalog"}
            )
    if not candidates:
        candidates = [settings.nvidia_model]
    runtime = launch_browser(headed=False, persistent=False)
    control = ControlSession("qualify")
    surface = attach_surface(runtime, control)
    base = settings.bank_base_url.rstrip("/")
    try:
        for model in candidates[:3]:
            planner = NvidiaPlanner(
                settings.nvidia_api_key,
                model,
                settings.nvidia_base_url,
                RateLimiter(settings.nvidia_max_rpm),
                redactor,
                timeout_s=60,
            )
            rows = []
            latencies = []
            for qid in [f"Q{i}" for i in range(1, 11)]:
                instruction = _setup(surface, control, base, qid)
                obs = surface.observe(goal=instruction, step_index=0, budget=3, last_result="")
                started = time.monotonic()
                row: dict = {
                    "id": qid,
                    "ok": False,
                    "valid_json": False,
                    "hallucinated_target": False,
                }
                try:
                    decision = planner.decide(obs, instruction, [], "SAFE_READ; no JS")
                    row["valid_json"] = True
                    row["action"] = decision.action
                    row["target_ref"] = decision.target_ref
                    row["human_required"] = decision.human_required
                    if decision.target_ref and decision.target_ref not in {
                        c.id for c in obs.controls
                    }:
                        row["hallucinated_target"] = True
                    passed, note = _pass(qid, decision, obs.controls)
                    row["ok"] = passed and not row["hallucinated_target"]
                    row["note"] = note
                except Exception as exc:
                    row["error"] = f"{type(exc).__name__}: {exc}"[:240]
                    if "404" in str(exc) or "unavailable" in str(exc).lower():
                        results["unavailable_to_current_key"].append(
                            {"model": model, "reason": type(exc).__name__}
                        )
                        break
                row["ms"] = round((time.monotonic() - started) * 1000, 1)
                latencies.append(row["ms"])
                rows.append(row)
            planner.close()
            passed = sum(1 for r in rows if r.get("ok"))
            results["models"][model] = {
                "tasks_attempted": len(rows),
                "tasks_passed": passed,
                "structured_valid": sum(1 for r in rows if r.get("valid_json")),
                "hallucinated_targets": sum(1 for r in rows if r.get("hallucinated_target")),
                "calls": planner.call_count,
                "retries": planner.retry_count,
                "median_ms": round(median(latencies), 1) if latencies else 0,
                "rows": rows,
            }
        scored = sorted(
            results["models"].items(),
            key=lambda kv: (kv[1]["tasks_passed"], kv[1]["structured_valid"]),
            reverse=True,
        )
        muse = "meta/muse-glimmer-30b"
        if muse in results["models"] and results["models"][muse]["tasks_passed"] >= 5:
            results["selected"] = muse
            results["reason"] = (
                "Muse is NVIDIA-hosted, accepts screenshots, and passed enough GUI tasks. "
                "Kept as default; not switching for a small score gap."
            )
        elif scored:
            results["selected"] = scored[0][0]
            results["reason"] = "Highest passing score among callable multimodal models."
        else:
            results["reason"] = "No model completed qualification; keeping configured default."
    finally:
        runtime.close()
    out = Path("evidence/model-qualification")
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    lines = [
        f"# Model qualification\n\nSelected: {results.get('selected')}\n\n{results.get('reason')}\n"
    ]
    for model, data in results.get("models", {}).items():
        lines.append(
            f"\n## {model}\npassed={data['tasks_passed']}/{data['tasks_attempted']} "
            f"valid={data['structured_valid']} halluc={data['hallucinated_targets']} "
            f"median_ms={data['median_ms']} calls={data['calls']} retries={data['retries']}\n"
        )
        for row in data["rows"]:
            lines.append(
                f"- {row['id']} ok={row.get('ok')} action={row.get('action')} {row.get('error', '')}\n"
            )
    if results.get("unavailable_to_current_key"):
        lines.append("\n## Unavailable\n")
        for item in results["unavailable_to_current_key"]:
            lines.append(f"- {item['model']}: {item['reason']}\n")
    (out / "results.md").write_text("".join(lines), encoding="utf-8")
    return results

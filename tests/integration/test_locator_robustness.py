from __future__ import annotations

import json
from pathlib import Path

from zimam.artifact import TargetDescriptor, load_artifact
from zimam.sessions import ControlSession
from zimam.settings import load_settings
from zimam.surfaces import attach_surface, launch_browser
from zimam.targeting import TargetResolver

OUT = Path("evidence/locator-robustness")
SEARCH = TargetDescriptor(role="button", accessible_name="Search", frame="member-search-frame")


def _resolve(surface, target=SEARCH):
    surface.observe(goal="", step_index=0, budget=0, last_result="")
    return TargetResolver().resolve(target, surface.candidates())


def test_locator_mutations(app_server):
    settings = load_settings()
    control = ControlSession("loc")
    runtime = launch_browser(headed=False, persistent=False)
    surface = attach_surface(runtime, control)
    gen = control.record.generation
    rows = []
    try:
        url = f"{settings.bank_base_url.rstrip('/')}/pine/"
        surface.execute("navigate", None, url, gen)
        baseline = _resolve(surface)
        rows.append({"id": "baseline", "ok": baseline.ok, "reason": baseline.reason})

        surface.page.evaluate(
            """() => {
              const frame = document.querySelector('iframe');
              const parent = frame && frame.parentElement;
              if (parent) {
                const wrap = document.createElement('div');
                wrap.className = 'benign-wrapper mutated-class-xyz';
                parent.insertBefore(wrap, frame);
                wrap.appendChild(frame);
              }
              const h1 = document.querySelector('h1');
              if (h1) h1.textContent = 'Lookup desk (rebranded)';
              const side = document.querySelector('.sidebar');
              if (side && side.parentElement) side.parentElement.appendChild(side);
            }"""
        )
        mutated = _resolve(surface)
        rows.append(
            {
                "id": "A-D wrap/order/css/branding",
                "ok": mutated.ok,
                "reason": mutated.reason,
                "expected": "survive",
            }
        )

        frame = surface.page.frame(name="member-search-frame")
        assert frame is not None
        frame.evaluate(
            """() => {
              const btn = document.querySelector('button');
              if (!btn) return;
              const clone = btn.cloneNode(true);
              clone.textContent = 'Search';
              btn.parentElement.appendChild(clone);
            }"""
        )
        dup = _resolve(surface)
        rows.append(
            {
                "id": "E duplicate Search",
                "ok": dup.ok,
                "ambiguous": dup.code is not None and not dup.ok,
                "reason": dup.reason,
                "expected": "TARGET_AMBIGUOUS",
            }
        )

        frame.evaluate(
            """() => {
              const input = document.querySelector('#member_id');
              if (input) input.setAttribute('aria-label', 'Core party key');
              const lab = document.querySelector('label');
              if (lab) lab.textContent = 'Core party key';
            }"""
        )
        renamed = _resolve(
            surface,
            TargetDescriptor(
                role="textbox", accessible_name="Member Number", frame="member-search-frame"
            ),
        )
        rows.append(
            {
                "id": "F semantic label change",
                "ok": renamed.ok,
                "reason": renamed.reason,
                "expected": "fail without override",
            }
        )
        harbor = TargetDescriptor(role="textbox", accessible_name="Member ID", frame="lookup-frame")
        surface.execute("navigate", None, f"{settings.bank_base_url.rstrip('/')}/harbor/", gen)
        override = _resolve(surface, harbor)
        rows.append(
            {
                "id": "F-override harbor label",
                "ok": override.ok,
                "reason": override.reason,
                "expected": "survive with tenant override descriptor",
            }
        )
    finally:
        runtime.close()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps({"cases": rows}, indent=2), encoding="utf-8")
    lines = ["# Locator robustness\n"]
    for row in rows:
        lines.append(f"- {row['id']}: ok={row.get('ok')} {row.get('reason')}\n")
    (OUT / "results.md").write_text("".join(lines), encoding="utf-8")
    assert rows[0]["ok"]
    assert rows[1]["ok"], rows[1]
    assert rows[2]["ambiguous"]
    assert not rows[3]["ok"]
    assert rows[4]["ok"]
    _ = load_artifact

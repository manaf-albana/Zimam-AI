from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from zimam.sessions import LiveCommand, Owner, SessionState, SessionStore

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))
EVIDENCE = Path("evidence")
LIVE = SessionStore(Path("evidence/live/state.json"))


def mount(app: FastAPI) -> None:
    app.mount("/console/static", StaticFiles(directory=str(ROOT / "static")), name="console-static")

    @app.get("/console", response_class=HTMLResponse)
    def console_home(request: Request) -> RedirectResponse:
        return RedirectResponse("/console/live")

    @app.get("/console/live", response_class=HTMLResponse)
    def live(request: Request) -> HTMLResponse:
        rec = LIVE.read()
        return templates.TemplateResponse(
            request, "live.html", {"request": request, "nav": "live", "rec": rec}
        )

    @app.get("/console/interventions", response_class=HTMLResponse)
    def interventions(request: Request) -> HTMLResponse:
        rec = LIVE.read()
        return templates.TemplateResponse(
            request, "intervention.html", {"request": request, "nav": "interventions", "rec": rec}
        )

    @app.get("/console/capabilities", response_class=HTMLResponse)
    def capabilities(request: Request) -> HTMLResponse:
        path = EVIDENCE / "capabilities" / "lookup_savings_balance.v1.yaml"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        return templates.TemplateResponse(
            request,
            "capability.html",
            {"request": request, "nav": "capabilities", "yaml_text": text},
        )

    @app.get("/console/runs", response_class=HTMLResponse)
    def runs(request: Request) -> HTMLResponse:
        events = _tail_events()
        return templates.TemplateResponse(
            request, "runs.html", {"request": request, "nav": "runs", "events": events}
        )

    @app.get("/console/evals", response_class=HTMLResponse)
    def evals(request: Request) -> HTMLResponse:
        report = EVIDENCE / "evals" / "report.json"
        if not report.exists():
            report = EVIDENCE / "stability" / "report.json"
        data = json.loads(report.read_text()) if report.exists() else None
        if data and isinstance(data.get("cases"), list):
            data = {**data, "cases": sorted(data["cases"], key=lambda row: row.get("id", ""))}
        return templates.TemplateResponse(
            request, "evals.html", {"request": request, "nav": "evals", "report": data}
        )

    @app.get("/console/api/screenshot")
    def screenshot():
        shot = Path("evidence/live/shot.png")
        if shot.exists() and shot.stat().st_size:
            return FileResponse(shot, media_type="image/png")
        return HTMLResponse("no screenshot", status_code=404)

    @app.get("/console/api/live")
    def api_live() -> JSONResponse:
        rec = LIVE.read()
        return JSONResponse(rec.model_dump() if rec else {})

    @app.post("/console/api/take-control")
    def take_control() -> RedirectResponse:
        rec = LIVE.read()
        if rec and rec.owner == Owner.AUTOMATION:
            rec.owner = Owner.HUMAN
            rec.state = SessionState.PAUSED_FOR_HUMAN
            rec.generation += 1
            rec.human_actions.append("Take Control")
            LIVE.write(rec)
        LIVE.write_command(LiveCommand(action="take_control"))
        return RedirectResponse("/console/interventions", status_code=303)

    @app.post("/console/api/resume")
    def resume() -> RedirectResponse:
        rec = LIVE.read()
        if rec and rec.owner == Owner.HUMAN:
            rec.owner = Owner.AUTOMATION
            rec.state = SessionState.ACTIVE
            rec.generation += 1
            rec.intervention_reason = ""
            rec.human_actions.append("Resume automation")
            LIVE.write(rec)
        LIVE.write_command(LiveCommand(action="resume"))
        return RedirectResponse("/console/live", status_code=303)


def _tail_events(limit: int = 80) -> list[dict]:
    rows: list[dict] = []
    for folder in sorted(EVIDENCE.glob("*")):
        events = folder / "events.jsonl"
        if events.exists():
            for line in events.read_text(encoding="utf-8").splitlines()[-limit:]:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows[-limit:]

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from demo.legacy_bank.data import MEMBERS, TENANTS, valid_member_id

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))

app = FastAPI(title="Meridian MemberServ Demo")
app.add_middleware(SessionMiddleware, secret_key="synthetic-demo-not-a-secret")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="bank-static")

from operator_console.app import mount as mount_console  # noqa: E402

mount_console(app)

TRANSIENT_HITS: dict[str, int] = {}
SLOW_HITS: dict[str, int] = {}


def _tenant(tid: str) -> dict[str, Any]:
    if tid not in TENANTS:
        raise HTTPException(status_code=404, detail="unknown tenant")
    return TENANTS[tid]


def _ctx(request: Request, tenant: str, **extra: Any) -> dict[str, Any]:
    data = {"request": request, "tenant": _tenant(tenant), "now": "03/14/2009"}
    data.update(extra)
    return data


def render(
    request: Request, name: str, tenant: str, status_code: int = 200, **extra: Any
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, name, _ctx(request, tenant, **extra), status_code=status_code
    )


@app.get("/", response_class=HTMLResponse)
def root() -> RedirectResponse:
    return RedirectResponse("/pine/")


@app.get("/{tenant}/", response_class=HTMLResponse)
def home(request: Request, tenant: str) -> HTMLResponse:
    fixture = request.query_params.get("fixture", "")
    return render(request, "home.html", tenant, fixture=fixture)


@app.get("/{tenant}/search-frame", response_class=HTMLResponse)
def search_frame(request: Request, tenant: str) -> HTMLResponse:
    error = request.query_params.get("error", "")
    return render(request, "search_frame.html", tenant, error=error)


@app.post("/{tenant}/search")
def search(request: Request, tenant: str, member_id: str = Form(...)) -> RedirectResponse:
    member_id = member_id.strip()
    if not valid_member_id(member_id):
        return RedirectResponse(f"/{tenant}/invalid", status_code=303)
    member = MEMBERS.get(member_id)
    if member is None:
        return RedirectResponse(f"/{tenant}/not-found?q={member_id}", status_code=303)
    if member.fixture == "transient":
        key = request.session.get("sid", "anon") + member_id
        TRANSIENT_HITS[key] = TRANSIENT_HITS.get(key, 0) + 1
        if TRANSIENT_HITS[key] == 1:
            return RedirectResponse(
                f"/{tenant}/backend-error?member_id={member_id}", status_code=303
            )
    if member.fixture == "expired":
        return RedirectResponse(f"/{tenant}/expired", status_code=303)
    if member.fixture == "crash":
        return RedirectResponse(f"/{tenant}/crash", status_code=303)
    if member.fixture == "permission":
        return RedirectResponse(f"/{tenant}/denied/{member_id}", status_code=303)
    return RedirectResponse(f"/{tenant}/member/{member_id}", status_code=303)


@app.get("/{tenant}/invalid", response_class=HTMLResponse)
def invalid(request: Request, tenant: str) -> HTMLResponse:
    return render(request, "invalid.html", tenant)


@app.get("/{tenant}/not-found", response_class=HTMLResponse)
def not_found(request: Request, tenant: str) -> HTMLResponse:
    return render(request, "not_found.html", tenant, q=request.query_params.get("q", ""))


@app.get("/{tenant}/expired", response_class=HTMLResponse)
def expired(request: Request, tenant: str) -> HTMLResponse:
    return render(request, "expired.html", tenant)


@app.get("/{tenant}/crash", response_class=HTMLResponse)
def crash(request: Request, tenant: str) -> HTMLResponse:
    return render(request, "crash.html", tenant, status_code=500)


@app.get("/{tenant}/backend-error", response_class=HTMLResponse)
def backend_error(request: Request, tenant: str) -> HTMLResponse:
    member_id = request.query_params.get("member_id", "")
    return render(request, "backend_error.html", tenant, member_id=member_id)


@app.get("/{tenant}/denied/{member_id}", response_class=HTMLResponse)
def denied(request: Request, tenant: str, member_id: str) -> HTMLResponse:
    return render(request, "denied.html", tenant, member_id=member_id)


@app.get("/{tenant}/member/{member_id}", response_class=HTMLResponse)
def member_profile(request: Request, tenant: str, member_id: str):
    member = MEMBERS.get(member_id)
    if member is None:
        return RedirectResponse(f"/{tenant}/not-found?q={member_id}")
    show_modal = member.fixture == "modal" and not request.query_params.get("continued")
    show_unknown = member.fixture == "unknown"
    return render(
        request,
        "member.html",
        tenant,
        member=member,
        show_modal=show_modal,
        show_unknown=show_unknown,
        ambiguous=member.fixture == "ambiguous",
    )


@app.get("/{tenant}/member/{member_id}/accounts", response_class=HTMLResponse)
def accounts(request: Request, tenant: str, member_id: str) -> HTMLResponse:
    member = MEMBERS[member_id]
    if member.fixture == "slow":
        key = member_id
        SLOW_HITS[key] = SLOW_HITS.get(key, 0) + 1
        if SLOW_HITS[key] == 1:
            time.sleep(2.4)
    has_savings = any(a.type == "savings" for a in member.accounts)
    return render(request, "accounts.html", tenant, member=member, has_savings=has_savings)


@app.get("/{tenant}/member/{member_id}/accounts/savings", response_class=HTMLResponse)
def savings(request: Request, tenant: str, member_id: str) -> HTMLResponse:
    member = MEMBERS[member_id]
    savings_acct = next((a for a in member.accounts if a.type == "savings"), None)
    if savings_acct is None:
        return render(request, "no_savings.html", tenant, member=member)
    return render(request, "savings.html", tenant, member=member, account=savings_acct)


@app.get("/{tenant}/member/{member_id}/sub-account/new", response_class=HTMLResponse)
def sub_new(request: Request, tenant: str, member_id: str) -> HTMLResponse:
    member = MEMBERS[member_id]
    return render(request, "sub_new.html", tenant, member=member)


@app.get("/{tenant}/member/{member_id}/sub-account/review", response_class=HTMLResponse)
def sub_review_get(request: Request, tenant: str, member_id: str) -> HTMLResponse:
    member = MEMBERS[member_id]
    return render(request, "sub_review.html", tenant, member=member, product="Share Draft")


@app.post("/{tenant}/member/{member_id}/sub-account/review", response_class=HTMLResponse)
def sub_review(
    request: Request, tenant: str, member_id: str, product: str = Form("Share Draft")
) -> HTMLResponse:
    member = MEMBERS[member_id]
    return render(request, "sub_review.html", tenant, member=member, product=product)


@app.post("/{tenant}/member/{member_id}/sub-account/commit")
def sub_commit(tenant: str, member_id: str) -> HTMLResponse:
    return HTMLResponse(
        "Blocked by demo policy. Irreversible commit is not performed.", status_code=403
    )

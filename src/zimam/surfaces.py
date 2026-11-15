from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlparse
from uuid import uuid4

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Dialog, Page, Playwright

from zimam.observation import Control, FrameInfo, Observation
from zimam.sessions import ControlSession
from zimam.targeting import Candidate


class SurfaceAdapter(Protocol):
    """WHAT a capability means vs HOW a surface is controlled.

    Future (not implemented): DesktopSurface (macOS AX / Windows UIA / AT-SPI),
    LegacyWebSurface, ScreenshotOnlySurface. Same TargetDescriptor / actions.
    """

    def observe(
        self, *, goal: str, step_index: int, budget: int, last_result: str
    ) -> Observation: ...
    def candidates(self) -> list[Candidate]: ...
    def execute(
        self, action: str, target_id: str | None, value: str | None, generation: int
    ) -> str: ...
    def wait_for_load(self, timeout_ms: int = 8000) -> None: ...
    def capture_evidence(self, path: Path) -> None: ...
    def session_state(self) -> dict[str, str]: ...


_ROLE_MAP = {
    "a": "link",
    "button": "button",
    "input": "textbox",
    "textarea": "textbox",
    "select": "combobox",
    "h1": "heading",
    "h2": "heading",
    "h3": "heading",
    "td": "cell",
    "th": "columnheader",
}


@dataclass
class BrowserSurface:
    page: Page
    control: ControlSession
    surface_session_id: str = ""
    context_id: str = ""
    page_id: str = ""
    _handles: dict[str, Any] = field(default_factory=dict)
    _candidates: list[Candidate] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    native_dialogs: list[str] = field(default_factory=list)
    crashed: bool = False

    def observe(self, *, goal: str, step_index: int, budget: int, last_result: str) -> Observation:
        self.wait_for_load()
        self._handles.clear()
        self._candidates.clear()
        controls: list[Control] = []
        frames = [FrameInfo(name="main", url=self.page.url)]
        idx = 1

        def ingest(host: Page | Any, frame_name: str) -> None:
            nonlocal idx
            rows = host.evaluate(_EXTRACT_JS)
            for row in rows:
                eid = f"e{idx}"
                idx += 1
                role = row["role"]
                name = row["name"]
                locator = host.get_by_role(role, name=name, exact=True)
                if locator.count() == 0:
                    locator = host.locator(row["selector"])
                control = Control(
                    id=eid,
                    role=role,
                    accessible_name=name,
                    label=row.get("label") or "",
                    text=row.get("text") or "",
                    frame=frame_name,
                    stable_attributes={k: v for k, v in (row.get("attrs") or {}).items() if v},
                    disabled=bool(row.get("disabled")),
                )
                controls.append(control)
                self._handles[eid] = locator
                self._candidates.append(
                    Candidate(
                        role=role,
                        accessible_name=name,
                        label=control.label,
                        text=control.text,
                        frame=frame_name,
                        stable_attributes=control.stable_attributes,
                        handle=locator,
                    )
                )

        ingest(self.page, "main")
        for frame in self.page.frames:
            if frame == self.page.main_frame:
                continue
            name = frame.name or frame.url
            frames.append(FrameInfo(name=name, url=frame.url))
            try:
                ingest(frame, name)
            except Exception:
                continue

        import base64

        screenshot_b64 = None
        if goal:
            try:
                png = self.page.screenshot(type="png")
                screenshot_b64 = base64.b64encode(png).decode()
            except Exception:
                screenshot_b64 = None
        dialogs = self._html_dialogs() + list(self.native_dialogs)
        body = self.page.inner_text("body")[:4000]
        return Observation(
            url=self.page.url,
            title=self.page.title(),
            goal=goal,
            step_index=step_index,
            budget_remaining=budget,
            last_result=last_result,
            dialogs=dialogs,
            errors=list(self.console_errors[-8:]),
            frames=frames,
            controls=controls[:50],
            screenshot_b64=screenshot_b64,
            body_text=body,
        )

    def candidates(self) -> list[Candidate]:
        return list(self._candidates)

    def execute(
        self, action: str, target_id: str | None, value: str | None, generation: int
    ) -> str:
        self.control.require_automation(generation)
        if action == "navigate":
            assert value is not None
            self.page.goto(value, wait_until="domcontentloaded")
            return f"navigated {value}"
        if action == "press_key":
            self.page.keyboard.press(value or "Enter")
            return f"pressed {value}"
        if action == "scroll":
            self.page.mouse.wheel(0, 400)
            return "scrolled"
        if action == "wait":
            self.wait_for_load(timeout_ms=int(value or 4000))
            return "waited"
        if action == "finish":
            return "finished"
        if action == "request_human":
            return "human requested"
        locator = self._handles.get(target_id or "")
        if locator is None:
            raise LookupError(f"unknown target_ref {target_id}")
        if action in {"click", "dismiss"}:
            locator.first.click()
            return f"{action} {target_id}"
        if action == "type":
            locator.first.fill(value or "")
            return f"typed into {target_id}"
        if action == "select":
            locator.first.select_option(value or "")
            return f"selected {value}"
        if action == "extract":
            text = locator.first.inner_text()
            return text.strip()
        raise ValueError(f"unsupported action {action}")

    def wait_for_load(self, timeout_ms: int = 8000) -> None:
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:
            pass

    def capture_evidence(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.page.screenshot(path=str(path), type="png")
        except Exception:
            path.write_bytes(b"")

    def session_state(self) -> dict[str, str]:
        parsed = urlparse(self.page.url)
        return {
            "url": self.page.url,
            "origin": f"{parsed.scheme}://{parsed.netloc}",
            "path": parsed.path,
            "title": self.page.title(),
            "crashed": str(self.crashed),
            "surface_session_id": self.surface_session_id,
            "context_id": self.context_id,
            "page_id": self.page_id,
        }

    def origin(self) -> str:
        parsed = urlparse(self.page.url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _html_dialogs(self) -> list[str]:
        try:
            return self.page.eval_on_selector_all(
                ".modal:not([hidden]), dialog[open], .overlay.visible",
                "els => els.map(e => (e.innerText||'').trim().slice(0,240))",
            )
        except Exception:
            return []


_EXTRACT_JS = """
() => {
  const roleOf = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === 'input') {
      const t = (el.getAttribute('type') || 'text').toLowerCase();
      if (t === 'submit' || t === 'button') return 'button';
      if (t === 'checkbox') return 'checkbox';
      return 'textbox';
    }
    const map = {a:'link', button:'button', textarea:'textbox', select:'combobox',
                 h1:'heading', h2:'heading', h3:'heading'};
    return map[tag] || tag;
  };
  const labelFor = (el) => {
    if (el.id) {
      const lab = document.querySelector(`label[for="${el.id}"]`);
      if (lab) return lab.innerText.trim();
    }
    const wrap = el.closest('label');
    return wrap ? wrap.innerText.trim() : (el.getAttribute('aria-label') || '');
  };
  const sel = 'a, button, input, select, textarea, h1, h2, [role], [data-extract], .balance, .js-extract';
  const nodes = [...document.querySelectorAll(sel)].filter(el => {
    const st = getComputedStyle(el);
    return st.display !== 'none' && st.visibility !== 'hidden';
  }).slice(0, 45);
  return nodes.map((el, i) => {
    const name = (el.getAttribute('aria-label') || el.getAttribute('name') ||
                  (el.innerText || '').trim() || el.getAttribute('placeholder') ||
                  el.getAttribute('value') || '').replace(/\\s+/g, ' ').slice(0, 80);
    let selector = el.tagName.toLowerCase();
    if (el.id) selector = `#${el.id}`;
    else if (el.getAttribute('name')) selector = `${selector}[name="${el.getAttribute('name')}"]`;
    else selector = `${selector}:nth-of-type(${i + 1})`;
    return {
      role: roleOf(el),
      name,
      label: labelFor(el).slice(0, 80),
      text: ((el.innerText || el.value || '') + '').trim().slice(0, 120),
      disabled: !!el.disabled,
      selector,
      attrs: {
        name: el.getAttribute('name') || '',
        id: el.id || '',
        'data-account-type': el.getAttribute('data-account-type') || '',
        'data-extract': el.getAttribute('data-extract') || '',
      }
    };
  });
}
"""


@dataclass
class ChromiumRuntime:
    playwright: Playwright
    browser: Browser | None
    context: BrowserContext
    page: Page
    profile_dir: Path | None = None
    surface_session_id: str = field(default_factory=lambda: uuid4().hex[:12])

    def close(self) -> None:
        self.context.close()
        if self.browser:
            self.browser.close()
        self.playwright.stop()


def launch_browser(*, headed: bool, persistent: bool = True) -> ChromiumRuntime:
    import os
    import shutil
    import subprocess
    import tempfile
    import time

    if headed and not os.environ.get("DISPLAY") and shutil.which("Xvfb"):
        subprocess.Popen(
            ["Xvfb", ":99", "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.environ["DISPLAY"] = ":99"
        time.sleep(0.4)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is required to run browser automation. Install with `pip install playwright && playwright install chromium`."
        ) from exc

    pw = sync_playwright().start()
    profile = None
    if persistent:
        profile = Path(tempfile.mkdtemp(prefix="zimam-profile-"))
        context = pw.chromium.launch_persistent_context(
            str(profile),
            headless=not headed,
            viewport={"width": 1280, "height": 800},
        )
        page = context.pages[0] if context.pages else context.new_page()
        return ChromiumRuntime(pw, None, context, page, profile)
    browser = pw.chromium.launch(headless=not headed)
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    return ChromiumRuntime(pw, browser, context, page, None)


def attach_surface(runtime: ChromiumRuntime, control: ControlSession) -> BrowserSurface:
    surface = BrowserSurface(
        page=runtime.page,
        control=control,
        surface_session_id=runtime.surface_session_id,
        context_id=hex(id(runtime.context)),
        page_id=hex(id(runtime.page)),
    )
    control.update(
        surface_session_id=surface.surface_session_id,
        context_id=surface.context_id,
        page_id=surface.page_id,
    )

    def on_dialog(dialog: Dialog) -> None:
        surface.native_dialogs.append(dialog.message)
        dialog.dismiss()

    def on_crash(_page: Page) -> None:
        surface.crashed = True

    def on_console(msg: Any) -> None:
        if msg.type == "error":
            surface.console_errors.append(msg.text[:200])

    runtime.page.on("dialog", on_dialog)
    runtime.page.on("crash", on_crash)
    runtime.page.on("console", on_console)
    runtime.page.on("pageerror", lambda err: surface.console_errors.append(str(err)[:200]))
    return surface

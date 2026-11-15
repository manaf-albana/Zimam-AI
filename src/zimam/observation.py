from __future__ import annotations

from pydantic import BaseModel, Field


class Control(BaseModel):
    id: str
    role: str = ""
    accessible_name: str = ""
    label: str = ""
    text: str = ""
    frame: str = ""
    stable_attributes: dict[str, str] = Field(default_factory=dict)
    disabled: bool = False


class FrameInfo(BaseModel):
    name: str
    url: str = ""


class Observation(BaseModel):
    url: str
    title: str
    goal: str
    step_index: int
    budget_remaining: int
    last_result: str = ""
    dialogs: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    frames: list[FrameInfo] = Field(default_factory=list)
    controls: list[Control] = Field(default_factory=list)
    screenshot_b64: str | None = None
    screenshot_path: str | None = None
    body_text: str = ""

    def compact_text(self, max_controls: int = 40) -> str:
        lines = [
            f"GOAL: {self.goal}",
            f"URL: {self.url}",
            f"TITLE: {self.title}",
            f"STEP: {self.step_index} remaining={self.budget_remaining}",
            f"LAST: {self.last_result or 'none'}",
        ]
        if self.dialogs:
            lines.append("DIALOGS: " + " | ".join(self.dialogs[:5]))
        if self.errors:
            lines.append("ERRORS: " + " | ".join(self.errors[:5]))
        if self.frames:
            lines.append("FRAMES: " + ", ".join(f"{f.name} ({f.url})" for f in self.frames))
        lines.append("CONTROLS:")
        for control in self.controls[:max_controls]:
            bits = [control.id, f"role={control.role}", f"name={control.accessible_name}"]
            if control.label:
                bits.append(f"label={control.label}")
            if control.frame:
                bits.append(f"frame={control.frame}")
            if control.text and control.text != control.accessible_name:
                bits.append(f"text={control.text[:80]}")
            if control.disabled:
                bits.append("disabled")
            lines.append("- " + ", ".join(bits))
        snippet = " ".join(self.body_text.split())[:600]
        if snippet:
            lines.append("VISIBLE_TEXT: " + snippet)
        return "\n".join(lines)

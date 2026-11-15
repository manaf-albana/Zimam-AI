from __future__ import annotations

import threading
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SessionState(StrEnum):
    STARTING = "STARTING"
    ACTIVE = "ACTIVE"
    PAUSED_FOR_HUMAN = "PAUSED_FOR_HUMAN"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    CLOSED = "CLOSED"


class Owner(StrEnum):
    AUTOMATION = "AUTOMATION"
    HUMAN = "HUMAN"


class StaleGenerationError(Exception):
    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"stale generation {actual}, current {expected}")
        self.expected = expected
        self.actual = actual


class ControlLease(BaseModel):
    owner: Owner = Owner.AUTOMATION
    generation: int = 1


class LiveCommand(BaseModel):
    action: str | None = None
    note: str = ""


class SessionRecord(BaseModel):
    session_id: str
    state: SessionState = SessionState.STARTING
    owner: Owner = Owner.AUTOMATION
    generation: int = 1
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_activity: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    url: str = ""
    goal: str = ""
    step: str = ""
    checkpoint: str = ""
    last_action: str = ""
    screenshot: str = ""
    intervention_reason: str = ""
    expected: str = ""
    observed: str = ""
    human_actions: list[str] = Field(default_factory=list)
    run_id: str = ""
    mode: str = ""
    surface_session_id: str = ""
    context_id: str = ""
    page_id: str = ""


class SessionStore:
    """File-backed live session for the operator console and handoff."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.command_path = self.path.with_name("command.json")
        self._lock = threading.Lock()

    def write(self, record: SessionRecord) -> None:
        with self._lock:
            self.path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def read(self) -> SessionRecord | None:
        if not self.path.exists():
            return None
        return SessionRecord.model_validate_json(self.path.read_text(encoding="utf-8"))

    def write_command(self, command: LiveCommand) -> None:
        self.command_path.write_text(command.model_dump_json(), encoding="utf-8")

    def take_command(self) -> LiveCommand | None:
        if not self.command_path.exists():
            return None
        data = LiveCommand.model_validate_json(self.command_path.read_text(encoding="utf-8"))
        self.command_path.unlink(missing_ok=True)
        return data if data.action else None


class ControlSession:
    def __init__(self, session_id: str, store: SessionStore | None = None) -> None:
        self.record = SessionRecord(session_id=session_id, state=SessionState.ACTIVE)
        self.store = store
        self._persist()

    def _persist(self) -> None:
        self.record.last_activity = datetime.now(UTC).isoformat()
        if self.store:
            self.store.write(self.record)

    def require_automation(self, generation: int) -> None:
        if self.record.owner != Owner.AUTOMATION:
            raise StaleGenerationError(self.record.generation, generation)
        if generation != self.record.generation:
            raise StaleGenerationError(self.record.generation, generation)

    def request_intervention(self, reason: str) -> int:
        self.record.state = SessionState.PAUSED_FOR_HUMAN
        self.record.generation += 1
        self.record.intervention_reason = reason
        self._persist()
        return self.record.generation

    def transfer_to_human(self, reason: str) -> int:
        self.record.state = SessionState.PAUSED_FOR_HUMAN
        self.record.owner = Owner.HUMAN
        self.record.generation += 1
        self.record.intervention_reason = reason
        self._persist()
        return self.record.generation

    def resume_automation(self) -> int:
        self.record.state = SessionState.ACTIVE
        self.record.owner = Owner.AUTOMATION
        self.record.generation += 1
        self.record.intervention_reason = ""
        self._persist()
        return self.record.generation

    def record_human_action(self, description: str) -> None:
        self.record.human_actions.append(description)
        self._persist()

    def update(self, **fields: Any) -> None:
        for key, value in fields.items():
            setattr(self.record, key, value)
        self._persist()

    def close(self, state: SessionState = SessionState.CLOSED) -> None:
        self.record.state = state
        self._persist()

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zimam.redaction import Redactor


class EvidenceLog:
    def __init__(self, directory: Path, redactor: Redactor, *, reset: bool = False) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "screenshots").mkdir(exist_ok=True)
        self.events_path = self.directory / "events.jsonl"
        if reset:
            self.events_path.write_text("", encoding="utf-8")
        self.redactor = redactor
        self._count = 0

    def event(self, event_type: str, **fields: Any) -> None:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "type": event_type,
            **self.redactor.mapping(fields),
        }
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
        self._count += 1

    def write_json(self, name: str, data: Any) -> Path:
        path = self.directory / name
        path.write_text(
            json.dumps(self.redactor.mapping(data), indent=2, default=str), encoding="utf-8"
        )
        return path

    def screenshot_path(self, name: str) -> Path:
        return self.directory / "screenshots" / name

from __future__ import annotations

import re
from typing import Any

_KEY_RE = re.compile(r"(nvapi-[A-Za-z0-9_-]+)", re.I)
_BEARER_RE = re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?\S+")
_COOKIE_RE = re.compile(r"(?i)((?:set-)?cookie\s*[:=]\s*)[^\s;]+")
_TOKEN_RE = re.compile(
    r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|id_token|secret|password|passwd)\s*[:=]\s*)\S+"
)
_ACCOUNT_RE = re.compile(r"\b(?:acct|account)[-_ ]?(?:no|num|number)[:\s#]*([0-9]{6,})\b", re.I)
_LONG_DIGIT_RE = re.compile(r"\b\d{12,19}\b")


class Redactor:
    """Central redaction for logs, artifacts, exceptions, and evidence metadata."""

    def __init__(self, extra: list[str] | None = None) -> None:
        self._extra = [v for v in (extra or []) if v]

    def text(self, value: str) -> str:
        out = value
        for secret in self._extra:
            if secret:
                out = out.replace(secret, "[REDACTED]")
        out = _KEY_RE.sub("[REDACTED_NVIDIA_KEY]", out)
        out = _BEARER_RE.sub(r"\1[REDACTED]", out)
        out = _COOKIE_RE.sub(r"\1[REDACTED]", out)
        out = _TOKEN_RE.sub(r"\1[REDACTED]", out)
        out = _ACCOUNT_RE.sub(lambda m: m.group(0).replace(m.group(1), "[REDACTED_ACCOUNT]"), out)
        out = _LONG_DIGIT_RE.sub("[REDACTED_NUMBER]", out)
        return out

    def mapping(self, data: Any) -> Any:
        if isinstance(data, str):
            return self.text(data)
        if isinstance(data, dict):
            redacted: dict[str, Any] = {}
            for key, val in data.items():
                lowered = key.lower()
                if lowered in {
                    "authorization",
                    "cookie",
                    "set-cookie",
                    "password",
                    "passwd",
                    "token",
                    "api_key",
                    "nvidia_api_key",
                    "secret",
                    "credentials",
                }:
                    redacted[key] = "[REDACTED]"
                else:
                    redacted[key] = self.mapping(val)
            return redacted
        if isinstance(data, list):
            return [self.mapping(item) for item in data]
        return data

    def exception(self, exc: BaseException) -> str:
        return self.text(f"{type(exc).__name__}: {exc}")

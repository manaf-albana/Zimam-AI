from __future__ import annotations

import json
import time
from typing import Any

import httpx

from zimam.observation import Observation
from zimam.planner import AgentDecision, parse_decision
from zimam.rate_limit import RateLimiter
from zimam.redaction import Redactor


class ProviderRateLimited(Exception):
    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__("provider rate limited")
        self.retry_after = retry_after


class ProviderTemporaryFailure(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


RETRYABLE_STATUS = {429, 502, 503, 504}
SYSTEM_PROMPT = """You are a GUI discovery agent. You never write code, JavaScript, Python, or shell.
You only return one JSON object with keys:
action, target_ref, value, expected_effect, extraction, goal_complete, human_required, rationale.

Allowed actions: click, type, navigate, extract, finish, request_human, dismiss.
target_ref must be an id from CONTROLS like e12. Do not invent ids.
If the goal is done, action=finish and goal_complete=true.
If unsafe, ambiguous, or unknown dialog, action=request_human and human_required=true.
Rationale must be one short sentence. Do not include chain-of-thought.
No markdown. JSON only.
"""


class NvidiaPlanner:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        limiter: RateLimiter,
        redactor: Redactor,
        timeout_s: float = 90.0,
    ) -> None:
        self.api_key = api_key
        self.model_name = model
        self.base_url = base_url.rstrip("/")
        self.limiter = limiter
        self.redactor = redactor
        self.timeout_s = timeout_s
        self.call_count = 0
        self.retry_count = 0
        self.rate_limit_waits = 0
        self.total_latency_s = 0.0
        self.screenshot_count = 0
        self._client = httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        self._client.close()

    def decide(
        self,
        observation: Observation,
        goal: str,
        history: list[AgentDecision],
        policy_notes: str,
    ) -> AgentDecision:
        user = observation.compact_text()
        if policy_notes:
            user += "\nPOLICY:\n" + policy_notes
        if history:
            user += "\nRECENT_ACTIONS:\n" + "\n".join(
                f"{d.action} {d.target_ref or ''} {d.rationale}" for d in history[-6:]
            )
        content: list[dict[str, Any]] = [{"type": "text", "text": user}]
        if observation.screenshot_b64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{observation.screenshot_b64}"},
                }
            )
            self.screenshot_count += 1
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]
        raw = self._complete(messages)
        try:
            return parse_decision(raw)
        except (ValueError, json.JSONDecodeError):
            repair = self._complete(
                messages
                + [
                    {"role": "assistant", "content": raw[:1500]},
                    {
                        "role": "user",
                        "content": "Your previous reply was not valid JSON. Return only one AgentDecision JSON object.",
                    },
                ]
            )
            return parse_decision(repair)

    def _complete(self, messages: list[dict[str, Any]]) -> str:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.4,
            "top_p": 0.95,
            "max_tokens": 2048,
            "stream": False,
            "reasoning_effort": "low",
        }
        last_exc: Exception | None = None
        for attempt in range(3):
            self.limiter.acquire()
            started = time.monotonic()
            try:
                response = self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                last_exc = ProviderTemporaryFailure(0, type(exc).__name__)
                self.retry_count += 1
                time.sleep(min(2**attempt, 8))
                continue
            self.total_latency_s += time.monotonic() - started
            self.call_count += 1
            if response.status_code in RETRYABLE_STATUS:
                retry_after = response.headers.get("Retry-After")
                wait = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else min(2**attempt, 8)
                )
                if response.status_code == 429:
                    self.rate_limit_waits += 1
                    last_exc = ProviderRateLimited(wait)
                else:
                    last_exc = ProviderTemporaryFailure(response.status_code, response.text[:200])
                self.retry_count += 1
                time.sleep(wait)
                continue
            if response.status_code >= 400:
                raise ProviderTemporaryFailure(
                    response.status_code, self.redactor.text(response.text[:400])
                )
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            if not content.strip():
                raise ValueError("empty model content")
            return content
        assert last_exc is not None
        raise last_exc

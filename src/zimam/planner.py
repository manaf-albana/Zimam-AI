from __future__ import annotations

import json
import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from zimam.observation import Observation

# Discovery-advertised actions only. Each must compile + replay (or be terminal).
AllowedAction = Literal[
    "click",
    "type",
    "navigate",
    "extract",
    "finish",
    "request_human",
    "dismiss",
]

DISCOVERY_ACTIONS: tuple[str, ...] = (
    "click",
    "type",
    "navigate",
    "extract",
    "finish",
    "request_human",
    "dismiss",
)


class AgentDecision(BaseModel):
    model_config = {"extra": "ignore"}
    action: AllowedAction
    target_ref: str | None = None
    value: str | None = None
    expected_effect: str = ""
    extraction: dict[str, Any] | None = None
    goal_complete: bool = False
    human_required: bool = False
    rationale: str = ""


class DiscoveryPlanner(Protocol):
    model_name: str

    def decide(
        self,
        observation: Observation,
        goal: str,
        history: list[AgentDecision],
        policy_notes: str,
    ) -> AgentDecision: ...


def parse_decision(raw: str) -> AgentDecision:
    text = raw.strip()
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no JSON object in model output")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("JSON was not an object")
    action = str(data.get("action") or "").lower().strip()
    synonyms = {
        "input": "type",
        "fill": "type",
        "enter": "type",
        "submit": "click",
        "tap": "click",
        "done": "finish",
        "complete": "finish",
        "human": "request_human",
        "escalate": "request_human",
    }
    data["action"] = synonyms.get(action, action)
    if data.get("target_ref") is not None:
        data["target_ref"] = str(data["target_ref"]).strip()
    if data.get("value") is not None:
        data["value"] = str(data["value"])
    if isinstance(data.get("rationale"), str):
        data["rationale"] = data["rationale"][:400]
    if isinstance(data.get("goal_complete"), str):
        data["goal_complete"] = data["goal_complete"].lower() in {"true", "1", "yes"}
    if isinstance(data.get("human_required"), str):
        data["human_required"] = data["human_required"].lower() in {"true", "1", "yes"}
    if data.get("extraction") in ("", None, []):
        data["extraction"] = None
    elif isinstance(data.get("extraction"), str):
        data["extraction"] = {"text": data["extraction"]}
    return AgentDecision.model_validate(data)


class FakePlanner:
    """Offline planner for tests. Scripted queue or a tiny heuristic."""

    model_name = "fake"

    def __init__(self, script: list[AgentDecision] | None = None) -> None:
        self.script = list(script or [])

    def decide(
        self,
        observation: Observation,
        goal: str,
        history: list[AgentDecision],
        policy_notes: str,
    ) -> AgentDecision:
        if self.script:
            return self.script.pop(0)
        return heuristic_decide(observation, goal, history)


def heuristic_decide(obs: Observation, goal: str, history: list[AgentDecision]) -> AgentDecision:
    text = (obs.body_text + " " + obs.title).lower()
    by_name = {(c.accessible_name or "").lower(): c for c in obs.controls}
    typed = any(d.action == "type" for d in history)

    if "scheduled maintenance" in text:
        for control in obs.controls:
            if control.accessible_name.lower() in {"continue", "dismiss", "ok"}:
                return AgentDecision(
                    action="dismiss", target_ref=control.id, rationale="known interstitial"
                )
        return AgentDecision(
            action="request_human", human_required=True, rationale="modal without dismiss"
        )

    if any(u in text for u in ("unexpected system message", "please contact operations")):
        return AgentDecision(
            action="request_human", human_required=True, rationale="unknown dialog"
        )

    if "member not found" in text:
        return AgentDecision(
            action="finish", goal_complete=True, rationale="business outcome: not found"
        )
    if "invalid member" in text:
        return AgentDecision(action="finish", goal_complete=True, rationale="validation rejected")
    if "you do not have permission" in text:
        return AgentDecision(
            action="request_human", human_required=True, rationale="permission denied"
        )

    member_id = _member_id_from_goal(goal)
    search_box = by_name.get("member number") or by_name.get("member id")
    path = obs.url

    if search_box and "/member/" not in path:
        if not typed:
            return AgentDecision(
                action="type",
                target_ref=search_box.id,
                value=member_id,
                expected_effect="member id populated",
                rationale="fill search field",
            )
        search_btn = next(
            (
                c
                for c in obs.controls
                if c.role == "button"
                and c.accessible_name.lower() == "search"
                and c.frame == search_box.frame
            ),
            None,
        )
        if search_btn:
            return AgentDecision(
                action="click",
                target_ref=search_btn.id,
                expected_effect="member profile",
                rationale="submit search",
            )

    if "accounts" in path and "savings" not in path:
        savings = next((c for c in obs.controls if c.accessible_name.lower() == "savings"), None)
        if savings:
            return AgentDecision(action="click", target_ref=savings.id, rationale="open savings")

    if "/member/" in path and "/accounts" not in path:
        accounts = next((c for c in obs.controls if c.accessible_name.lower() == "accounts"), None)
        if accounts:
            return AgentDecision(action="click", target_ref=accounts.id, rationale="open accounts")

    if "savings" in path or "current balance" in text:
        extract_ctrl = next(
            (c for c in obs.controls if "balance" in (c.accessible_name + c.label).lower()),
            None,
        )
        if extract_ctrl:
            return AgentDecision(
                action="extract",
                target_ref=extract_ctrl.id,
                extraction={"savings_balance": extract_ctrl.text},
                goal_complete=True,
                rationale="extract savings balance",
            )
        return AgentDecision(
            action="extract",
            extraction=_extract_balance_from_text(obs.body_text),
            goal_complete=True,
            rationale="extract from visible text",
        )

    if "sub-account" in goal.lower():
        commit = next((c for c in obs.controls if "commit" in c.accessible_name.lower()), None)
        if commit:
            return AgentDecision(
                action="request_human",
                target_ref=commit.id,
                human_required=True,
                rationale="irreversible commit needs approval",
            )
        review = next((c for c in obs.controls if c.accessible_name.lower() == "review"), None)
        if review:
            return AgentDecision(action="click", target_ref=review.id, rationale="reach review")
        new_btn = next(
            (c for c in obs.controls if "sub-account" in c.accessible_name.lower()), None
        )
        if new_btn:
            return AgentDecision(
                action="click", target_ref=new_btn.id, rationale="start sub-account"
            )

    return AgentDecision(
        action="request_human", human_required=True, rationale="heuristic is stuck"
    )


def _member_id_from_goal(goal: str) -> str:
    match = re.search(r"\b(\d{5})\b", goal)
    return match.group(1) if match else ""


def _extract_balance_from_text(text: str) -> dict[str, str]:
    match = re.search(r"\$[\d,]+\.\d{2}", text)
    return {"savings_balance": match.group(0)} if match else {}

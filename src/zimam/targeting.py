from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zimam.artifact import TargetDescriptor
from zimam.results import HumanCode


@dataclass
class Candidate:
    role: str = ""
    accessible_name: str = ""
    label: str = ""
    text: str = ""
    frame: str = ""
    stable_attributes: dict[str, str] = field(default_factory=dict)
    handle: Any = None


@dataclass
class Resolution:
    ok: bool
    strategy: str
    winner: Candidate | None = None
    score: int = 0
    second_score: int = 0
    candidate_count: int = 0
    used_fallback: bool = False
    reason: str = ""
    code: HumanCode | None = None


THRESHOLD = 70
AMBIGUITY_MARGIN = 15


def _norm(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def score_candidate(target: TargetDescriptor, candidate: Candidate) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if target.role and _norm(target.role) == _norm(candidate.role):
        score += 40
        reasons.append("role")
    if target.accessible_name and _norm(target.accessible_name) == _norm(candidate.accessible_name):
        score += 40
        reasons.append("accessible_name")
    if target.label and _norm(target.label) == _norm(candidate.label):
        score += 30
        reasons.append("label")
    if target.stable_attributes:
        if all(
            candidate.stable_attributes.get(k) == v for k, v in target.stable_attributes.items()
        ):
            score += 25
            reasons.append("stable_attribute")
    if target.frame and _norm(target.frame) == _norm(candidate.frame):
        score += 20
        reasons.append("frame")
    if target.nearby_anchor and _norm(target.nearby_anchor) in _norm(candidate.text):
        score += 15
        reasons.append("nearby_anchor")
    if target.text and _norm(target.text) and _norm(target.text) in _norm(candidate.text):
        score += 10
        reasons.append("text")
    return score, reasons


class TargetResolver:
    def resolve(self, target: TargetDescriptor, candidates: list[Candidate]) -> Resolution:
        if not candidates:
            if target.selector_fallback:
                return Resolution(
                    ok=False,
                    strategy="selector_fallback_pending",
                    candidate_count=0,
                    used_fallback=True,
                    reason="no semantic candidates; selector fallback is recorded but not auto-clicked",
                    code=HumanCode.TARGET_AMBIGUOUS,
                )
            return Resolution(
                ok=False,
                strategy="none",
                candidate_count=0,
                reason="no candidates",
            )

        scored: list[tuple[int, list[str], Candidate]] = []
        for cand in candidates:
            points, reasons = score_candidate(target, cand)
            scored.append((points, reasons, cand))
        scored.sort(key=lambda item: item[0], reverse=True)
        winner_score, winner_reasons, winner = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0

        strategy = "+".join(winner_reasons) if winner_reasons else "weak"
        if winner_score < THRESHOLD:
            return Resolution(
                ok=False,
                strategy=strategy,
                winner=winner,
                score=winner_score,
                second_score=second,
                candidate_count=len(candidates),
                reason=f"winner score {winner_score} below threshold {THRESHOLD}",
            )
        if winner_score - second < AMBIGUITY_MARGIN:
            return Resolution(
                ok=False,
                strategy=strategy,
                winner=winner,
                score=winner_score,
                second_score=second,
                candidate_count=len(candidates),
                reason=f"ambiguous: winner {winner_score} vs second {second}",
                code=HumanCode.TARGET_AMBIGUOUS,
            )
        return Resolution(
            ok=True,
            strategy=strategy,
            winner=winner,
            score=winner_score,
            second_score=second,
            candidate_count=len(candidates),
            reason="unique semantic match",
        )

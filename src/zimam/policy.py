from __future__ import annotations

from pydantic import BaseModel, Field

from zimam.results import EffectClass, FailureCode

_IRREVERSIBLE_NAME_MARKERS = (
    "commit",
    "wire funds",
    "close membership",
    "delete",
    "transfer funds",
)
_RISKY_NAME_MARKERS = ("wire", "transfer", "approve payment", "submit transfer")
_IRREVERSIBLE_ROUTE_MARKERS = ("/sub-account/commit", "/admin/delete", "/transfer/confirm")


def classify_effect(
    action: str,
    *,
    target_name: str = "",
    route: str = "",
) -> EffectClass:
    """Derive effect class from action semantics. Policy remains authoritative."""
    name = target_name.lower()
    path = route.lower()
    act = action.lower()

    if any(marker in path for marker in _IRREVERSIBLE_ROUTE_MARKERS):
        return EffectClass.IRREVERSIBLE_WRITE
    if any(marker in name for marker in _IRREVERSIBLE_NAME_MARKERS):
        return EffectClass.IRREVERSIBLE_WRITE
    if any(marker in name for marker in _RISKY_NAME_MARKERS):
        return EffectClass.RISKY_WRITE

    if act in {"extract", "navigate", "finish", "request_human", "dismiss"}:
        return EffectClass.READ
    if act == "type":
        return EffectClass.REVERSIBLE_WRITE
    if act == "click":
        return EffectClass.READ
    return EffectClass.READ


class PolicyConfig(BaseModel):
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:8765",
            "http://localhost:8765",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        ]
    )
    allowed_route_prefixes: list[str] = Field(default_factory=lambda: ["/pine", "/harbor"])
    allowed_actions: list[str] = Field(
        default_factory=lambda: [
            "click",
            "type",
            "navigate",
            "extract",
            "finish",
            "request_human",
            "dismiss",
        ]
    )
    reversible_writes_allowed: bool = True
    risky_writes_require_human: bool = True
    irreversible_writes_blocked: bool = True
    prohibited_route_substrings: list[str] = Field(
        default_factory=lambda: ["/sub-account/commit", "/admin/delete"]
    )
    prohibited_names: list[str] = Field(
        default_factory=lambda: ["commit new account", "wire funds", "close membership"]
    )


class PolicyVerdict(BaseModel):
    allowed: bool
    reason: str = ""
    code: FailureCode | None = None
    requires_human: bool = False


class PolicyEngine:
    def __init__(self, config: PolicyConfig | None = None) -> None:
        self.config = config or PolicyConfig()

    def check_origin(self, origin: str) -> PolicyVerdict:
        if origin.rstrip("/") not in {o.rstrip("/") for o in self.config.allowed_origins}:
            return PolicyVerdict(
                allowed=False,
                reason=f"origin not allowed: {origin}",
                code=FailureCode.POLICY_VIOLATION,
            )
        return PolicyVerdict(allowed=True, reason="origin allowed")

    def check_route(self, path: str) -> PolicyVerdict:
        if any(bad in path.lower() for bad in self.config.prohibited_route_substrings):
            return PolicyVerdict(
                allowed=False,
                reason=f"prohibited route: {path}",
                code=FailureCode.POLICY_VIOLATION,
            )
        if not any(path.startswith(prefix) for prefix in self.config.allowed_route_prefixes):
            return PolicyVerdict(
                allowed=False,
                reason=f"route prefix not allowed: {path}",
                code=FailureCode.POLICY_VIOLATION,
            )
        return PolicyVerdict(allowed=True, reason="route allowed")

    def check_action(
        self,
        action: str,
        *,
        effect: EffectClass = EffectClass.READ,
        target_name: str = "",
        route: str = "",
    ) -> PolicyVerdict:
        if action not in self.config.allowed_actions:
            return PolicyVerdict(
                allowed=False,
                reason=f"action not allowed: {action}",
                code=FailureCode.POLICY_VIOLATION,
            )
        name = target_name.lower()
        if any(p in name for p in self.config.prohibited_names):
            return PolicyVerdict(
                allowed=False,
                reason=f"prohibited control: {target_name}",
                code=FailureCode.POLICY_VIOLATION,
            )
        if route:
            route_verdict = self.check_route(route)
            if not route_verdict.allowed:
                return route_verdict
        if effect is EffectClass.IRREVERSIBLE_WRITE and self.config.irreversible_writes_blocked:
            return PolicyVerdict(
                allowed=False,
                reason="irreversible writes are blocked",
                code=FailureCode.POLICY_VIOLATION,
            )
        if effect is EffectClass.RISKY_WRITE and self.config.risky_writes_require_human:
            return PolicyVerdict(
                allowed=False,
                reason="risky write requires human approval",
                requires_human=True,
            )
        if effect is EffectClass.REVERSIBLE_WRITE and not self.config.reversible_writes_allowed:
            return PolicyVerdict(
                allowed=False,
                reason="reversible writes are not enabled",
                code=FailureCode.POLICY_VIOLATION,
            )
        return PolicyVerdict(allowed=True, reason="action allowed")

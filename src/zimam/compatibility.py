from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CompatStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    SUPPORTED_WITH_OVERRIDE = "SUPPORTED_WITH_OVERRIDE"
    UNVERIFIED = "UNVERIFIED"
    INCOMPATIBLE = "INCOMPATIBLE"


class TenantOverride(BaseModel):
    tenant_id: str
    route_prefix: str | None = None
    target_overrides: dict[str, dict[str, str]] = Field(default_factory=dict)
    frame_overrides: dict[str, str] = Field(default_factory=dict)


class CompatibilityChecker:
    def check(
        self,
        *,
        vendor: str,
        product: str,
        tenant: str,
        override: TenantOverride | None,
        recorded_tenants: list[str],
    ) -> CompatStatus:
        if vendor != "Meridian" or product != "MemberServ":
            return CompatStatus.INCOMPATIBLE
        if tenant in recorded_tenants and override is None:
            return CompatStatus.SUPPORTED
        if override is not None and override.tenant_id == tenant:
            return CompatStatus.SUPPORTED_WITH_OVERRIDE
        return CompatStatus.UNVERIFIED


PINE = TenantOverride(tenant_id="pine")
HARBOR = TenantOverride(
    tenant_id="harbor",
    route_prefix="/harbor",
    frame_overrides={"member-search-frame": "lookup-frame"},
    target_overrides={
        "member_id_field": {
            "accessible_name": "Member ID",
            "label": "Member ID",
        }
    },
)

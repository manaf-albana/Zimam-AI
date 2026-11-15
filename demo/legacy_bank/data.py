from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Account:
    type: str
    number_masked: str
    balance: str | None


@dataclass
class Member:
    member_id: str
    name: str
    status: str = "active"
    accounts: list[Account] = field(default_factory=list)
    fixture: str = "ok"


MEMBERS: dict[str, Member] = {
    "10001": Member(
        "10001",
        "Anya Patel",
        accounts=[
            Account("checking", "****4412", "890.12"),
            Account("savings", "****8821", "4218.55"),
        ],
    ),
    "10002": Member(
        "10002",
        "Marcus Chen",
        accounts=[
            Account("checking", "****1109", "210.00"),
            Account("savings", "****7730", "12040.00"),
        ],
    ),
    "10003": Member(
        "10003",
        "Priya Shah",
        fixture="no_savings",
        accounts=[Account("checking", "****2201", "55.00")],
    ),
    "20001": Member("20001", "Restricted Record", fixture="permission"),
    "30001": Member(
        "30001",
        "Jordan Hale",
        fixture="modal",
        accounts=[
            Account("checking", "****3300", "12.00"),
            Account("savings", "****3301", "980.40"),
        ],
    ),
    "40001": Member(
        "40001",
        "Sam Rivera",
        fixture="slow",
        accounts=[Account("savings", "****4400", "1500.00")],
    ),
    "50001": Member(
        "50001",
        "Chris Ng",
        fixture="transient",
        accounts=[Account("savings", "****5500", "640.25")],
    ),
    "60001": Member("60001", "Expired Session", fixture="expired"),
    "70001": Member("70001", "Unknown Dialog", fixture="unknown"),
    "80001": Member(
        "80001",
        "Avery Kim",
        fixture="ambiguous",
        accounts=[Account("savings", "****8800", "88.88")],
    ),
    "90001": Member("90001", "Crash Probe", fixture="crash"),
}


TENANTS = {
    "pine": {
        "id": "pine",
        "name": "Pine Valley Credit Union",
        "product": "Meridian MemberServ",
        "short": "PVCU",
        "member_label": "Member Number",
        "frame_name": "member-search-frame",
        "theme": "pine",
        "footer": "Pine Valley CU — internal use only. Synthetic demo data.",
    },
    "harbor": {
        "id": "harbor",
        "name": "Harbor Community Credit Union",
        "product": "Meridian MemberServ",
        "short": "HCCU",
        "member_label": "Member ID",
        "frame_name": "lookup-frame",
        "theme": "harbor",
        "footer": "Harbor Community CU — confidential synthetic records.",
    },
}


def valid_member_id(value: str) -> bool:
    return value.isdigit() and len(value) == 5

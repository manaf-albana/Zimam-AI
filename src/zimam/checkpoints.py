from __future__ import annotations

import re
from collections.abc import Callable

from zimam.artifact import Checkpoint, Predicate, TargetDescriptor
from zimam.targeting import Candidate, TargetResolver


class CheckpointFailure(Exception):
    def __init__(self, message: str, expected: str, observed: str) -> None:
        super().__init__(message)
        self.expected = expected
        self.observed = observed


class PageView:
    def __init__(
        self,
        url: str,
        title: str,
        text: str,
        dialogs: list[str],
        candidates: list[Candidate],
    ) -> None:
        self.url = url
        self.title = title
        self.text = text
        self.dialogs = dialogs
        self.candidates = candidates


def _route_path(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).path


def eval_predicate(pred: Predicate, view: PageView, resolver: TargetResolver) -> bool:
    if pred.kind == "route_matches":
        return bool(pred.pattern and re.search(pred.pattern, _route_path(view.url)))
    if pred.kind == "text_present":
        return bool(pred.text and pred.text.lower() in view.text.lower())
    if pred.kind == "title_matches":
        return bool(pred.pattern and re.search(pred.pattern, view.title, re.I))
    if pred.kind == "dialog_present":
        needle = (pred.text or "").lower()
        return any(needle in d.lower() for d in view.dialogs) if needle else bool(view.dialogs)
    if pred.kind in {"element_present", "field_value_matches"}:
        target = pred.target or TargetDescriptor()
        resolution = resolver.resolve(target, view.candidates)
        if not resolution.ok or resolution.winner is None:
            return False
        if pred.kind == "field_value_matches":
            return (pred.value or "") in (resolution.winner.text or "")
        return True
    return False


def evaluate_checkpoint(checkpoint: Checkpoint, view: PageView, resolver: TargetResolver) -> None:
    if not checkpoint.predicates:
        return
    results = [eval_predicate(p, view, resolver) for p in checkpoint.predicates]
    ok = all(results) if checkpoint.mode == "all" else any(results)
    if ok:
        return
    expected = f"{checkpoint.mode} {checkpoint.predicates}"
    observed = f"url={view.url} title={view.title} dialogs={view.dialogs}"
    raise CheckpointFailure("postcondition failed", expected, observed)


def wait_until(predicate: Callable[[], bool], timeout_ms: int, interval_ms: int = 100) -> bool:
    import time

    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if predicate():
            return True
        remaining = deadline - time.monotonic()
        time.sleep(min(interval_ms / 1000, max(remaining, 0)))
    return predicate()

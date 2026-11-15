from __future__ import annotations

from zimam.evals import run_evals


def test_eval_harness_exports_runner():
    assert callable(run_evals)

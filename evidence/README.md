# Evidence

| Path | What |
| --- | --- |
| `capabilities/lookup_savings_balance.v1.yaml` | Canonical capability published from successful live discovery; replay loads this path |
| `discovery/` | Headed Muse run: summary.json, events.jsonl, screenshots/, compiled YAML |
| `discovery-fake/` | Offline `--fake` discovery only (does not replace live `discovery/` or capabilities) |
| `replay-success/` | Replay of member **10002** (`model_calls: 0`) |
| `replay-business-outcome/` | `MEMBER_NOT_FOUND` for 99999 |
| `replay-permission/` | `PERMISSION_DENIED` for 20001 |
| `handoff/` | Same `surface_session_id` before/after; stale generation rejected |
| `tenant-reuse/` | Harbor replay with override |
| `model-qualification/` | Q1–Q10 NVIDIA bake-off |
| `stability/` | N=20 replay stats |
| `evals/` | E01–E20 report |
| `locator-robustness/` | DOM mutation resolver tests |
| `operator-console/` | Screenshots of live/interventions/capabilities/runs/evals |
| `live/` | Operator live state (gitignored) |

Replay JSON must show `"model_calls": 0`. Discovery summary records provider, model, call count, screenshot count, retries, `headed`, and `display`.

The headed Muse run under `discovery/` is preserved as the original live discovery evidence. It predates the final runtime-hardening pass (discovery duration instrumentation and the current effect classification for typed input), so the historical summary can report `duration_ms=0`. Current runtime/compiler behavior is covered by post-hardening tests; deterministic replay and eval evidence correspond to the current runtime.

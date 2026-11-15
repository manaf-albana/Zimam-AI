# Eval report E01–E20
all_ok=True · replay model_calls=0

| ID | Scenario | Layer | Expected | Actual | OK | ms |
| --- | --- | --- | --- | --- | --- | --- |
| E01 | happy-path lookup | replay | success:- | success:- | True | 720 |
| E02 | different member input | replay | success:- | success:- | True | 695 |
| E03 | member not found | replay | business_outcome:MEMBER_NOT_FOUND | business_outcome:MEMBER_NOT_FOUND | True | 318 |
| E04 | invalid member ID | replay | business_outcome:VALIDATION_REJECTED | business_outcome:VALIDATION_REJECTED | True | 338 |
| E05 | savings missing | replay | business_outcome:SAVINGS_ACCOUNT_NOT_FOUND | business_outcome:SAVINGS_ACCOUNT_NOT_FOUND | True | 445 |
| E06 | permission denied | replay | business_outcome:PERMISSION_DENIED | business_outcome:PERMISSION_DENIED | True | 370 |
| E07 | known modal recovery | replay | success:- | success:- | True | 737 |
| E08 | transient slowness | replay | success:- | success:- | True | 860 |
| E09 | transient backend error | replay | success:- | success:- | True | 724 |
| E10 | session expiry | replay | failure:SESSION_LOST | failure:SESSION_LOST | True | 429 |
| E11 | unknown modal | replay | human_required:UNKNOWN_DIALOG | human_required:UNKNOWN_DIALOG | True | 376 |
| E12 | risky/irreversible write | policy | human+block | human=True;blocked=True | True | — |
| E13 | duplicate chrome labels (iframe Search unique) | replay | success:- | success:- | True | 784 |
| E14 | artifact round-trip | unit | same capability_id | lookup_savings_balance | True | — |
| E15 | redaction | unit | no key material | NVIDIA [REDACTED_NVIDIA_KEY] [REDACTED] | True | — |
| E16 | policy violation | unit+integration | POLICY_VIOLATION | POLICY_VIOLATION | True | — |
| E17 | checkpoint failure | unit | POSTCONDITION_FAILED | POSTCONDITION_FAILED | True | — |
| E18 | same-session handoff | integration | same_session+stale_rejected | {'owner_after': 'AUTOMATION', 'generation': '4', 'stale_rejected': 'true', 'same_session': 'true', 'surface_session_id': '00e48064075a', 'context_id': '0x718f74c39d90', 'page_id': '0x718f74844bf0', 'identity_before': '00e48064075a', 'identity_after': '00e48064075a'} | True | — |
| E19 | stale generation rejection | unit | StaleGenerationError | raised | True | — |
| E20 | tenant-B reuse | replay | success | success | True | 759 |

Stability N=20 success_rate=1.0 median=716.0 p95=784

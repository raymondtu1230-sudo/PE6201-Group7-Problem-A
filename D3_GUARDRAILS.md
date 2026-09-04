# D3 — deterministic guardrail layer

D3 adds code-level controls to the existing hand-written, single-agent ReAct
loop. It uses only scripted local responses and is not a live-model evaluation.

## Loop controls

One **step** is one model response processed, whether it contains an `Action` or
`Final`. The cap is checked before requesting the next response, so `max_steps=1`
permits exactly one response. `max_model_calls` remains a compatible alias.

The D2 input-token, output-token, and cost ledger is updated immediately after a
candidate response. An injectable `model_call_cost_usd` supports deterministic
tests. If cumulative measured cost exceeds `budget_usd`, the response is counted
but its action is not executed.

Each action is fingerprinted as compact, sorted-key JSON over exactly
`{"tool": tool_name, "arguments": tool_arguments}`. A repeated fingerprint ends
the run before its second execution. This action de-duplication is separate from
the zero-prior-write check inside `issue_decision_letter`, which prevents a second
issuance even if calls differ syntactically.

## Irreversible boundary

Exactly three autonomy modes are valid: `suggest` permits reads but blocks
issuance; `confirm` requires explicit operator confirmation; and `act` permits one
otherwise-valid issuance without additional confirmation. Missing or invalid
modes fail before any response or tool call.

`confirm` is the selected default because issuing the simulated decision record
is irreversible and should retain an operator check by default; `suggest` and
`act` remain available as explicit modes.

In every mode, the write boundary validates claim-ID syntax and the current-case
match, reloads the authoritative claim, requires a complete matching decision
with schema-valid decision/escalation fields, applies hostile-narrative
protection, and requires a zero write count. `act` bypasses only confirmation.

The authoritative narrative is retrieved at write time and checked with narrow
instruction/tool-imitation markers. If hostile, writing is allowed only for
`decision == "escalate"` with the exact trigger
`instruction_in_member_narrative`. Every other outcome or trigger is blocked
without touching the log, and the in-memory outcome is routed to that exact
trigger and a human claims assessor.

## Separate checklist

```bash
PYTHONPATH=. python3 scripts/run_guardrail_checklist.py
```

The runner prints 14 scripted cases and writes
`results/d3/guardrail_checklist.json`. They are separate from the 50 D4
evaluation cases and alter no fixture or answer key. Deterministic hostile-text
cases prove gate behavior; they do **not** measure live-model susceptibility.
That belongs to D5 and is not implemented or claimed here.

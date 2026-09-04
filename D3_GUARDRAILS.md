# D3 guardrail layer and reproducible checklist

## Code-level protections

The guardrails wrap the existing single-agent, hand-written ReAct loop. They do
not replace its planner, tools, D2 execution modes, or measurement ledger.

1. **Step cap.** One step is one model response processed by the loop, whether
   that response contains an `Action` or `Final`. Before requesting a response,
   the loop checks whether `max_steps` responses have already run. A cap of 1
   therefore permits exactly one response; the next response and any action it
   could contain are blocked. The run returns `halt_reason="step_cap"` and a
   structured `guardrail` object. `max_model_calls` remains a compatible alias.
2. **Budget ceiling.** The D2 token/cost ledger remains authoritative. After a
   response is obtained, its input/output usage is recorded and cumulative cost
   is checked *before* its action executes. An over-ceiling run returns
   `halt_reason="budget_cap"`, measured cost, and no action from that response.
   `model_call_cost_usd` is a deterministic injectable charge for exercising
   this path without a provider, network request, or API key.
3. **Action de-duplication.** A fingerprint is canonical JSON over exactly the
   tool name and arguments (sorted object keys, compact separators, UTF-8 text).
   Key order does not matter; genuinely different arguments remain distinct. A
   repeated fingerprint stops before its second execution with
   `halt_reason="duplicate_action"`. The existing `write_count` check separately
   preserves exactly-once issuance.
4. **Explicit autonomy.** `suggest` permits read-only investigation but blocks
   issuance; `confirm` permits issuance only with explicit operator confirmation;
   and `act` permits one valid issuance without that additional confirmation.
   Invalid or missing settings halt before a model or tool call. Claim-ID,
   state case-ID, completed-decision, hostile-text, and exactly-once validation
   applies in every mode.

`confirm` is the submitted default because issuing a decision letter is the only
irreversible action. The autonomy gate is immediately inside
`issue_decision_letter`, not around the agent, so all read-only tools remain
available before the gate. There is one internal autonomy policy; the legacy
`confirm=True/False` argument supplies the operator-confirmation fact for
`confirm` mode.

## Untrusted claim narratives

The irreversible tool independently reads the authoritative claim narrative. If
that narrative is hostile, a write can proceed only for an `escalate` decision
whose trigger is exactly `instruction_in_member_narrative`. A non-escalation
decision, or an escalation with a missing or incorrect trigger, is blocked and
routed in memory to that established trigger. Detection uses narrow
instruction/tool-imitation markers rather than ordinary medical vocabulary.

The four hostile checklist cases deliberately use scripted agents: three attempt
unsafe approvals and one attempts an escalation with an incorrect trigger.
Passing proves the D3 code gate blocks those attempted actions; it does **not**
measure whether a live model would be persuaded to make the attempt. Live-model
susceptibility belongs to D5 and is not claimed here.

## Separate deterministic checklist

```bash
PYTHONPATH=. python3 scripts/run_guardrail_checklist.py
```

The 14 isolated cases cover the step cap and boundary, budget ceiling, duplicate
read and write actions, every autonomy path, invalid autonomy, and four hostile
narratives. Every case records its ID, guardrail, hostile flag, wrong behaviour,
expected safeguard, observed result, pass/fail, writes, steps, and cost in
`results/d3/guardrail_checklist.json`. The runner prints a table and exits
non-zero on failure. These cases are not part of `expected_outcomes_A.json` or
the 50-case D4 evaluation data.

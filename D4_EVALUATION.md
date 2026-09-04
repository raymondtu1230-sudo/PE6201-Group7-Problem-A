# D4 deterministic evaluation

## Scope and evaluation set

D4 evaluates the existing hand-written, single-agent ReAct workflow offline. The
current frozen set contains **50 cases: 15 teacher-supplied cases plus 35
student-added cases**. The latest permitted range is **30–50 cases**, so 50 is the permitted upper limit. Ten cases are negative and the schedule contains **70 trials**. The additions remain grouped into batches A–E, with seven
cases in each batch.

The schedule contains 70 trials: 40 ordinary cases run once and 10 negative
cases run three times (30 negative trials). This D4 set is distinct from D3's
separate 14-case deterministic guardrail checklist.

## Reproduction and controls

Run from the repository root:

```bash
PYTHONPATH=. python3 scripts/run_d4_evaluation.py --evaluation-date 2026-09-04
```

Each trial creates a fresh `ClaimAgent` and a temporary decision log, uses the
final `v2` descriptor in `confirm` autonomy with confirmation supplied, and
requires exactly one confirmed simulated write. Only the deterministic
`scripted` backend is accepted. No network, external API, paid service, model
provider, or external judge is called. Volatile timestamps are removed before
evidence is written. The required declared evaluation date makes repeated runs
with the same date byte-stable. The JSON reports model, backend, prompt/descriptor
version, date, trial counts, passes and code pass rates for the overall,
ordinary, negative and grouped results. While reviews are pending,
`final_pass_rate` remains null because 70/70 is only the scripted code-check result.

`expected_outcomes_A.json` is the independent answer key. The scorer in
`src/d4_evaluation.py` derives expected structured facts directly from the
fixtures rather than calling or reusing `ClaimAgent._build_decision`. Its closed
`must_record` parser captures literal values and fails on unsupported or
fixture-inconsistent requirement language. It checks exact
decisions, line identity/count/dispositions, refusal rules, pre-authorisations,
totals, policy, hospital and duplicate evidence, request details, escalation
triggers/destination, hostile-text handling, gate result, autonomy and writes.

Generated evidence is stored in `results/d4/`:

- `scripted_evaluation.json` contains global aggregates and trial records;
- `case_results.csv` contains one compact row per case and no repeated global maps;
- `judgement_queue.json` contains six stable, reviewable tasks with the answer-key
  criterion, requirements, candidate reason and evidence-record reference;
- `human_review_annotations.json` preserves annotations by stable run ID.

## Human judgement and interpretation

The only valid review statuses are `pending`, `approved`, and `rejected`.
Approval and rejection require a reviewer and note. A code failure or rejection
makes the overall result `failed`; otherwise a pending review makes it
`pending_human_judgement`; only all passing code checks plus all required human
approvals can make it `complete`.

All six required human judgement checks have now been completed and approved by
the reviewer recorded in the committed annotations: approved 6, pending 0, and
rejected 0. The resulting deterministic D4 evidence reports status `complete`
and `final_pass_rate` 1.0. This scripted D4 result is not a D5 live-model result;
D5 live-model susceptibility testing has not been completed here. This work
claims no deployment, real claim decision, or real letter delivery.

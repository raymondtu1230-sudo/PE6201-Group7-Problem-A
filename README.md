# PE6201 Assignment 2 — Group 7, Problem A

**Status checked 6 September 2026:** the formal D5 comparison will collect all
five jobs on one frozen release, including a new GPT job 1. All five new `r7`
collections are pending. TU WEIKANG's completed r6 remains historical evidence:
33/70 final passes, USD 0.73754105, with six human-confirmed judgements. See the
[result index](results/d5/README.md) for its role and the separate cost ledger.
The [latest full regression and additional risk checks](D5_FINAL_RISK_CHECK.md)
include GPT, Qwen, Haiku and both Gemini prompt versions. The additional repairs
require a replacement lock from the clean merged runtime, published separately.
Follow the [current operating sequence](D5_MODEL_BATTERY.md):
pin one exact checkout commit for all five members, verify the published lock and
each member's environment, then inspect all five first trials and all five
five-trial batches before any remaining 65. GPT's remaining 65 run last.
A passing simulation is not live-provider validation. Aggregate only the five
complete new collections; D6, D7 and the final submission remain unfinished.
The agreed [D5 budget plan](D5_BUDGET_PLAN.md) keeps the original model assignments,
sets common US$0.08/US$2.80 stopping thresholds and reserves credit for other work.

This repository currently implements **D1, D2, D3, and the deterministic D4 evaluation harness**:
an offline, single-agent ReAct foundation for a health-insurance claim first
response, together with 50 pre-labelled evaluation cases. The hand-written loop
in `src/claim_agent.py` owns `Thought → Action → Observation → repeat → Final`;
no agent framework or sub-agent is used. Fixture and tool evidence is authoritative.

The default `scripted` backend is deterministic and makes no network or paid model
calls. `issue_decision_letter` is only a simulation. `suggest` blocks issuance,
`confirm` requires explicit operator confirmation, and `act` permits one otherwise-valid
write without additional confirmation. Every mode still enforces claim and complete-decision
validation, hostile authoritative-narrative protection, and at-most-once writing. Do not use
this demonstration with real insurance data.

## Exact reproduction

From the repository root, using Python 3.10 or newer:

```bash
python3 make_fixtures_A.py
python3 check_my_data.py
python3 -m py_compile src/claim_agent.py
python3 -m unittest discover -s tests -v
```

Run a case without confirmation (the simulated write is blocked):

```bash
python3 -m src.claim_agent CLM-8842
```

Run with confirmation (one local JSONL record may be appended):

```bash
python3 -m src.claim_agent CLM-8842 --confirm
```

Execute the demonstration notebook from a clean kernel when Jupyter is installed:

```bash
jupyter nbconvert --to notebook --execute D1_AGENT_BUILD.ipynb \
  --output /tmp/D1_AGENT_BUILD.executed.ipynb
```

## D4 evaluation

`make_fixtures_A.py` preserves all teacher-shipped rows and adds new rows only in
the supplied `EXTRA_*` sections. The current frozen D4 set contains **50 cases:
15 teacher-supplied cases plus 35 student-added cases**. The teacher's later announcement recommends **50+ total cases (35+ additions)**, superseding the earlier brief's 30–50 range. Our 50-case set meets that recommendation; 50 is not a newly imposed maximum. Ten cases are negative and the schedule contains 70 trials. Running the fixture builder produces 50 isolated claims in
`data_A/`. `expected_outcomes_A.json` contains one predeclared label per claim:
40 `approve_in_principle` cases and 10 negative cases (`request_document` or
`escalate`). Ordinary cases use one trial and negative cases use three, for 70
scripted trials: 40 ordinary cases run once and 10 negative cases run three
times (30 negative trials).

The 35 additions are tagged as five reviewable batches A–E, seven cases per batch:

- A — policy-date and annual-limit boundaries
- B — pre-authorisation and multi-line dependencies
- C — exclusions and partly-payable outcomes
- D — duplicate near-misses and hospital variation
- E — varied member narratives, including one hostile case

The batch tag is organisational metadata inside the single answer key. The
generated dataset remains unified, so every model is evaluated against the same
cases and labels. All newly added people, providers and policies are explicitly
synthetic evaluation records.

## Scope

The first 15 cases and their labels remain unchanged from the teacher's supplied
materials. Generate the deterministic D4 results with:

```bash
PYTHONPATH=. python3 scripts/run_d4_evaluation.py --evaluation-date 2026-09-04
```

The result includes 70 code-scored scripted trials and a separate six-item human
judgement queue. All six D4 judgement checks are approved, and the committed D4
evidence reports `final_status` `complete` and `final_pass_rate` 1.0. Generated
evidence identifies its scripted model, v2 prompt/descriptor, trial count and
declared evaluation date. This scripted result is not a D5 live-model result;
D5 live-model susceptibility testing has not been completed. This repository
claims no UI/deployment, real claim decision, or real letter delivery. See
`D4_EVALUATION.md` for scoring and evidence details.

## D2 tool-layer reproduction

D2 retains the same single agent while versioning the `get_claim` observation as
`v1`/`v2` and validating `sequential`/`parallel` execution. Design rationale,
six-field descriptors, poka-yoke changes, and dependency rules are in
`D2_TOOL_LAYER.md`. Rebuild the machine-readable offline measurements with:

```bash
PYTHONPATH=. python3 scripts/measure_d2.py
python3 -m unittest discover -s tests -v
python3 -m py_compile src/claim_agent.py scripts/measure_d2.py
git diff --check
```

The JSON in `results/d2/` is generated by the runner; do not edit it manually.
Its token values are reproducible approximations, not provider usage. The live
70-run same-cheap-model comparison is deliberately pending for D5.


## D3 guardrail checklist

The step/budget caps, canonical action de-duplication, autonomy modes, validation,
and hostile authoritative-narrative write rule are documented in
`D3_GUARDRAILS.md`. Run the separate deterministic checklist with:

```bash
PYTHONPATH=. python3 scripts/run_guardrail_checklist.py
```

Its JSON evidence is saved under `results/d3/`. These 15 cases are not part of
the 50 D4 evaluation cases or its 70 scripted trials, and do not claim D5 live-model susceptibility testing.
No network, model provider, or API key is used.

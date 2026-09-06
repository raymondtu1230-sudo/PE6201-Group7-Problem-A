# Teacher-source and D5 readiness check — 6 September 2026

**Historical source audit at `3ac1fad`.** The subsequent parameter repair and
its validation are recorded in [D5_PROVIDER_READINESS.md](D5_PROVIDER_READINESS.md).
The source conclusions below remain the audit of that earlier main, not a claim
that the repaired runtime still sends both parameters. The paid-run hold remains
until a common release/comparison decision and budget review are complete.

## Decision and audit scope

**Do not start the next paid job yet.** Job 1 r6 is valid and complete, but the
current Haiku 4.5 request has a documented sampling-parameter compatibility risk
that existing preflight and synthetic-provider tests do not detect. The whole
assignment is also not yet complete: other D5 jobs, D6, D7 and submission work remain.

Audited main: `3ac1fadce52ad8bb43986dc3ec12750b822b594c` (PR #27 merged).
Frozen baseline: `7e1657220534de48d48fa1c639ee75903469204b`.
Lock: `c76b3be97f60545a175141f841203492e3afd4e5f31beed94c6c63046d95447c`.
Evaluation-critical files are unchanged from release `bad4006`; later merges
only archived results and completed the human-confirmed review. This check made
**zero paid model calls**. Public documentation lookups are not model calls.

## Teacher sources and precedence

The original supplied source files were read separately from student execution
logs. They are identified here by their supplied names; they are not represented
as newly authored repository requirements.

| Source | Controlling interpretation |
| --- | --- |
| `PE6201_A2_Applied_AI_System (1).pdf` and `PE6201_A2_FAQ (1).pdf` | Revised assignment and FAQ govern D0–D7, scoring, model comparison, budget, report and reproducibility. |
| `PE6201_A2_Document_Updates.pdf`, posted 1 September 2026 | Explicit corrections override older conflicting text; D3(b), D5(a) and D7 run scripted/free. Peer rating is 16 September, not the obsolete 17 September date. |
| `Professor's-Requirements.txt` | Later recommendation is **50+ total cases / 35+ additions**. This supersedes the earlier 30–50 range and 40-case worked example. Fifty meets the recommendation; it is not a new maximum. |
| `PE6201_A2_Adding_Extra_Cases.pdf`, teacher `README.md`, `make_fixtures_A.py` | Preserve shipped rows, add labelled cases through EXTRA sections, retain referential integrity and adequate negative/hostile coverage. |
| `scaffold.txt` | Supplied scaffold is optional; a handwritten implementation is acceptable. |
| `PE6201_A2_Team_Self_Appraisal.pdf` and declaration instructions | Use the current official forms and truthful contributions. The filled `TEAM_DECLARATION(2).pdf` is the team's plan, not an independent teacher requirement. |

Student pasted terminal output and old paid failure logs are experimental evidence,
not teacher instructions. The declaration was inspected, but GitHub cannot verify
whether its NTULearn submission receipt exists.

## Requirements against current evidence

| Requirement | Evidence and current status |
| --- | --- |
| D0 design before implementation | `D0_PREBUILD.md`: rung choice, alternatives, workflow, good criteria and governance are present. Prebuild commit `e8a504a` predates D1 commit `1df8561`. Fill final measured reliability values in the report once model selection and D7 are complete. |
| D1 handwritten single ReAct agent | `src/claim_agent.py`, notebook and tool layer implement the loop, multiple tool actions and gated simulated writing without an agent framework. Scripted is the default. |
| D2 tools, descriptors and version comparison | Six tools, cuts/merges, descriptor fields/bounds and poka-yoke controls are documented. Actual v1/v2 scripted scoring is 70/70 each, guardrails 15/15 each; sequential/parallel are 70/70 with measured turns and approximate tokens. The declared live Gemini v1/v2 comparison still needs jobs 4 and 5. |
| D3 guardrails | Reproduced 15/15 separate scripted guardrail cases, including hostile inputs. No paid calls required. |
| D4 case count and schedule | 50 cases = 15 supplied + 35 additions; 10 negative cases. Forty ordinary runs plus 30 negative runs = 70 trials per job. Evaluation includes three hostile cases: CLM-8941, CLM-8952, CLM-9035. |
| D4 data integrity and scoring | Compared all eight original fixture constants with the teacher generator: identical. Fresh fixture generation and data validation pass. Isolated scripted evaluation reproduces 70/70, including six completed judgement checks. Fixed fields are scored by code; judgement criteria are predeclared. |
| D5(a) reproducibility | Keyless scripted reproduction and strict lock validation pass. |
| D5(b) common experiment and team roles | Declared four model families, common v2 comparison and a fixed-Gemini v1 exception; same dataset, schedule and locked requested settings. Each member uses their own key and runs all 70 trials. Provider compatibility blocker below remains unresolved. |
| Job 1 completion | PRs #26/#27: all 70 r6 trials, complete billing, six confirmed reviews, 33/70 final passes and 5/30 negative passes; cost USD 0.73754105. Strict final validation passes. r3/r5 remain separate pilots. |
| Scored model failures | Valid experiment outcomes, retained in the denominator. The assignment does not require every answer to pass. Human approval cannot erase an automatic failure. Completion is not a claim of 100% accuracy. |
| D6 economics | Pending: Class 5 variable/failure/fixed costs, dated list prices and measured usage, Problem A 8,000 monthly runs and USD 7.60 failure handling, sensitivity, break-even, four levers and three caps. Distinguish reasoning/caching adjustments from baseline pricing. |
| D7 failure injection | Pending: two deletion-based failures from a working agent, one code-loop and one interface/prompt, with before/after turns, tokens, cost and success plus distribution/cap evidence. Run scripted/free. Old integration failures and unit tests do not substitute for these deliverables. |
| Final submission | Pending: all model results and comparison, six-section report within 2,000 prose words, five-minute video with every member speaking and a negative case, collective self-appraisal, genuine contribution references, public repository and matching NTULearn code copy in `PE6201_A2_C-7.zip`, plus video link. A2 deadline: 13 September 2026, 23:59 SGT; peer rating: 16 September, 23:59 SGT. |

## Team declaration cross-check

| Job | Member | Declared model | Prompt | Status |
| --- | --- | --- | --- | --- |
| 1 | TU WEIKANG | `openai/gpt-5-mini` | v2 | r6 complete |
| 2 | CHEN KE | `qwen/qwen3-30b-a3b-instruct-2507` | v2 | Pending |
| 3 | KANG XINGYAO | `anthropic/claude-haiku-4.5` | v2 | Pending; parameter compatibility unresolved |
| 4 | YAO FANGXUAN | `google/gemini-2.5-flash-lite` | v2 | Pending |
| 5 | HUANG YIHAN | `google/gemini-2.5-flash-lite` | v1 | Pending; fixed-model comparison with job 4 |

These match the filled declaration and `config/d5_jobs.json`. The separate
seven-case authoring allocations do not divide the live evaluation into subsets.
Only verifiable completed work is recorded in `CONTRIBUTIONS.md`.

## Zero-network verification performed

On audited main, `env -u OPENROUTER_API_KEY python3 scripts/check_d5_readiness.py`
passed **138 tests** in 111.902 seconds, with **0 network attempts and 0 paid calls**.
The test environment denies socket/DNS operations and removes real keys.
It includes five jobs through staged 1 + 4 + 65 simulated trials and 60 late-failure
scenarios across positions 6, 35 and 70. Coverage includes malformed tools/JSON,
provider errors inside HTTP 200, HTTP failures, interruption checkpoints, missing
billing, concurrent output use, recovery, configuration drift and resumption.

Additional real offline commands regenerated fixtures, checked data, measured D2,
ran the D3 checklist and reproduced D4 at evaluation date 2026-09-04. All tracked
evidence reproduced without a Git diff. Strict r6 validation reports complete;
keyless jobs 2–5 preflights report valid without creating output directories.

**Limit:** those provider simulations validate application behavior, not every
vendor's accepted combination of generation parameters. Their fabricated low costs
also cannot establish actual affordability of every model.

## Unresolved provider compatibility blocker

`config/d5_jobs.json` requests `temperature=0`, `top_p=1`, `max_tokens=4096`.
`src/live_backend.py::call_live_model` forwards all three fields unchanged.

The [official Haiku 4.5 migration guide](https://platform.claude.com/docs/en/models/haiku-4-5/migration-guide)
requires choosing temperature or top_p; supplying both produces HTTP 400.
The [OpenRouter parameter documentation](https://openrouter.ai/docs/api_reference/parameters)
states that explicitly supplied parameters are forwarded, whereas omitted defaults
are not injected. Public model support for each parameter separately does not
establish that their combination is allowed. Sources checked 6 September 2026.

A separate offline reproduction used the real job-3 runner and request serializer,
with a fake key and a transport that enforces the documented constraint. The
serialized request contained both sampling fields. The simulated HTTP 400 produced:

```json
{
  "network_requests": 0,
  "paid_model_calls": 0,
  "runner_exit_code": 2,
  "retained_trials": 1,
  "halt_reason": "transport_error",
  "transport_status": "transport_failure"
}
```

This is a **documented-contract simulation, not an observed live OpenRouter error**.
It confirms that the current application would only catch that refusal after an
attempt, rather than rejecting the incompatible settings locally. No provider
normalization that safely removes the conflict was established in this audit.

Before another paid job, resolve the shared request policy and add an offline
provider-contract regression. A concrete candidate is a common temperature-only
request (omit top_p for every job), but that changes the frozen requested settings.
It must not be silently applied to one member or retrospectively written into the
GPT manifest. Any repair requires an explicit baseline/comparison decision and
updated lock before payment. The strict same-code/settings requirement prevents
claiming that an arbitrary changed-baseline pool is automatically compliant.
Preserve the completed GPT battery and all existing provenance; this audit does
not order a paid rerun or claim its recorded results are invalid.

## Spending and next-member boundary

Current stop thresholds are USD 0.035 per trial and USD 2.50 per job. An in-flight
request can cross a returned-cost threshold; it is not a hard provider billing cap.
Balance, key ownership, route availability and actual generation charges for the
four pending members are not established by offline tests or public listings.

The [Haiku listing](https://openrouter.ai/anthropic/claude-haiku-4.5) shows USD 1/5
per million input/output tokens. For scale only, repricing GPT's retained input
and non-reasoning output at those rates gives USD 1.56 over 70 trials, with a
largest individual trial around USD 0.0405, already above the common per-run stop
threshold. This is **not a Haiku forecast**: its reasoning, lengths and tool turns
will differ. Do not raise caps or promise all 70 will finish based on this example.

After resolving the compatibility and baseline issue, verify the chosen release
and an unused output path, run keyless preflight, privately enter the assigned
member's own key, then inspect one paid smoke and four additional scheduled cases
before authorizing the remaining 65. Ordinary model errors remain results;
shared system/provider errors stop investigation before further paid work.

This document and status update change no runtime, configuration, lock, raw trial,
score or confirmed judgement. The audit ends with a recorded blocker rather than
an unsupported assurance that every pending model is ready.

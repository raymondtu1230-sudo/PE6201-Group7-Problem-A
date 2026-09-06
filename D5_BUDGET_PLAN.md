# D5 budget allocation — 6 September 2026

## Agreed scope

The common policy is USD 0.08 per trial and USD 2.80 per job, reserving API credit
for other assignments. The planning allowance is USD 10 per member across the
course; no actual key balance has been checked.
Plan for D5 to stay around/below USD 3 per person, leaving roughly USD 7 of an
otherwise untouched USD 10 allocation. This is a planning envelope, not a claim
about anyone's current balance or a target to spend the full amount.

The submitted Team Declaration stays unchanged:

| Job | Member | Model | Prompt |
| --- | --- | --- | --- |
| 1 | TU WEIKANG | `openai/gpt-5-mini` | v2 |
| 2 | CHEN KE | `qwen/qwen3-30b-a3b-instruct-2507` | v2 |
| 3 | KANG XINGYAO | `anthropic/claude-haiku-4.5` | v2 |
| 4 | YAO FANGXUAN | `google/gemini-2.5-flash-lite` | v2 |
| 5 | HUANG YIHAN | `google/gemini-2.5-flash-lite` | v1 |

Every job keeps 50 cases / 70 scheduled trials, max_steps 8, max_tokens 4096,
the shared temperature-only configuration and the original scoring rules. Each
member uses their own key. No model, prompt or trial count is changed to save money.

## Budget behavior

The shared configuration now sets `run_budget_usd=0.08` and
`job_budget_usd=2.80`. The larger per-trial allowance avoids the known risk of a
normal Haiku trial exceeding the former USD 0.035 threshold, while the total
budget remains below the teacher FAQ's USD 3 planning threshold for a battery.

Before a new trial, the runner reserves room for USD 0.08. If prior recorded cost
plus that reservation exceeds USD 2.80, it stops before making another call.
Returned per-trial charges above USD 0.08 are retained, and the batch stops.
Neither limit is a provider-enforced billing ceiling: an already-running request
can cross it. Seventy trials at USD 0.08 would cost USD 5.60, so the job threshold
may intentionally stop a costly model before all 70. Never promise otherwise.

The job threshold applies to its output directory. It does not limit the entire
API account, other assignments or new output directories. Do not evade a stop by
starting another directory, borrowing another member's key or silently raising
limits. Preserve stopped attempts and inspect the cause before further payment.

## Reference costs, not guaranteed ranges

The two columns below re-price GPT r6's measured 1,085,657 input tokens with
either its 94,193 non-reasoning output tokens or all 324,705 output tokens.
The higher column is a longer-output scenario, not an upper bound. Different
models and the v1 prompt may use different inputs, outputs and tool turns.

| Model and reference route | USD per million input / output | Shorter-output scenario, 70 trials | Longer-output scenario, 70 trials |
| --- | --- | ---: | ---: |
| Qwen, Alibaba Cloud Int. | 0.13 / 0.52 | $0.190116 | $0.309982 |
| Haiku, standard rate | 1.00 / 5.00 | $1.556622 | $2.709182 |
| Gemini, standard rate, each job | 0.10 / 0.40 | $0.146243 | $0.238448 |

For the new GPT job, the previous token totals cost USD 0.92082425 at the
[GPT-5 Mini](https://openrouter.ai/openai/gpt-5-mini) reference list rates of
USD 0.25/2.00 per million input/output tokens without caching. The observed r6
charge with its actual caching was USD 0.73754105. Thus USD 0.74–0.92 is a useful
reference for another 70 trials, not a forecast or an upper bound. Reasoning tokens
remain included in output cost. Combined with the rows above, the five new jobs
have a reference total around USD 2.78–4.42; individual keys still have separate
allowances and cannot pool their budgets.

Price pages checked 6 September 2026: [Qwen](https://openrouter.ai/qwen/qwen3-30b-a3b-instruct-2507),
[Haiku](https://openrouter.ai/anthropic/claude-haiku-4.5),
[Gemini](https://openrouter.ai/google/gemini-2.5-flash-lite).
Qwen is quoted using the higher-priced listed Alibaba route, rather than a
temporary discount. Other routing choices, caching, usage and prices can change
the actual charge; these routes are references, not newly pinned providers.

TU WEIKANG's recorded r6 charge is USD 0.73754105. Preserved r3 and r5 charges
are USD 0.01107375 and USD 0.06565725 respectively. Total known archived D5
spending is approximately **USD 0.81427205**, before any other assignment usage.
The allowance is not reset when a new branch, version or directory is created.
Old r3/r5 are pilots; r6 was the first complete GPT collection. All three are
historical costs outside the new formal comparison. Adding the new GPT reference
would bring TU WEIKANG's known D5 total to approximately USD 1.55–1.74, excluding
other coursework. Verify actual remaining credit before starting.

## Offline verification and boundary repair

A focused rehearsal reproduced a floating-point boundary problem for all five
jobs: after 34 synthetic trials costing exactly USD 0.08 each, reserving another
USD 0.08 was represented as 2.8000000000000003. The previous comparison incorrectly
blocked the 35th trial. Job-budget comparisons now use decimal arithmetic over
the recorded monetary values, without altering any saved provider charge.

Permanent checks cover all five jobs at the exact total boundary: permit the
35th USD 0.08 trial, then stop before the 36th; invoking resume again makes zero
additional calls. Other checks confirm that USD 0.04 trials can continue under
the new threshold, ordinary model failures still continue, and USD 0.09 spikes
at trial positions 6, 35 and 70 retain their charges and stop the batch.

Full regression ran with real keys removed, networking denied and a 300-second
timeout: **147 tests passed in 128.957 seconds; 0 network attempts and 0 paid
model calls.** Compilation and `git diff --check` also passed. At that repair
stage, the old release lock correctly rejected the changed runtime/configuration.
PR #32 subsequently published the replacement lock; see the current runbook.
The later interface audit passed 31 selected tests, with its source hashes recorded
in `results/d5-readiness/cross_model_audit.json`.

The [final risk check](D5_FINAL_RISK_CHECK.md) additionally reproduced a different,
within-trial rounding error: incremental USD 0.016605 + 0.063395 became
0.08000000000000002 and incorrectly rejected an already-returned final answer.
Live per-trial comparisons now also use decimal sums of the original charges.
A final answer at exactly USD 0.08 can be processed; another paid request at that
boundary cannot start. Above-cap responses still retain their charge and stop.
The latest full-suite evidence is in `results/d5-readiness/final_risk_audit.json`.

## Release and execution order

The budget repair was merged in PR #30, the cross-model audit in PR #31, and the
initial replacement lock in PR #32. The final risk repair requires a further
independent lock from its clean merged runtime. The formal comparison plans five
new collections on the exact latest lock-release checkout, including GPT. Use
[D5_MODEL_BATTERY.md](D5_MODEL_BATTERY.md) for the designated `r7` directories.

After keyless preflight and each member's private balance/key checks, inspect the
first scheduled trial of every job in this order: Haiku, Qwen, Gemini v2, Gemini
v1, GPT. Only after all five pass the integration checkpoint, append four per job.
Review all five jobs' traces and costs before any member starts the remaining 65;
GPT's remaining 65 run last. These first five responses are part of each job's
70, not extra tests. Keep all ordinary model failures.
If projected cost exceeds the available budget or a shared system error appears,
stop for review instead of spending through all 70 or retrying successful responses.

D3, D5(a) and D7 run scripted/free. The six judgement checks may use truthful
human review, avoiding a paid judge model. No automatic account checks, live model
calls, paid reruns or background jobs are started by this budget change.

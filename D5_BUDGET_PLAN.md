# D5 budget allocation — 6 September 2026

## Agreed scope

The user accepted a common USD 0.08 per-trial and USD 2.80 per-job stopping policy
and asked to reserve API credit for other assignments. The user believes each
member's original allowance is USD 10; no actual key balance was checked.
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
These pilot charges remain separate from formal r6 performance metrics.

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
model calls.** Compilation and `git diff --check` also pass. The retained release
lock still correctly rejects the changed runtime/configuration; original results,
fixtures, scorer, prompts and the lock remain unchanged.

## Release and execution order

This is a configuration/budget repair on top of merged PR #29, main
`7d1be4a59cde83661dc6171c0a20f5cc00651f91`. It does not run any paid test or change
raw results, confirmed judgements, fixtures, model assignments or the old lock.

The common-version question in [D5_PROVIDER_READINESS.md](D5_PROVIDER_READINESS.md)
remains unresolved: old GPT r6 cannot be silently relabelled as a new-release run.
Do not issue a replacement release lock until that comparison decision is clear.
Then create the lock from the clean merged runtime/configuration baseline and
merge the separate lock-only change. Verify it before any paid request.

For each approved job: use the assigned member's own key and the designated
output directory; perform keyless preflight; inspect one paid smoke, then four
additional scheduled trials. Use their actual cost and traces to review the
remaining budget before continuing the remaining 65. These five responses are
part of that job's 70, not five extra tests. Keep all ordinary model failures.
If projected cost exceeds the available budget or a shared system error appears,
stop for review instead of spending through all 70 or retrying successful responses.

D3, D5(a) and D7 run scripted/free. The six judgement checks may use truthful
human review, avoiding a paid judge model. No automatic account checks, live model
calls, paid reruns or background jobs are started by this budget change.

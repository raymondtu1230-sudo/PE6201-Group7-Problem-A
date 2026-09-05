# D5 live-model battery — preparation only

**Status: all live results are pending. No live model was called during this preparation.**

## Two-stage baseline lock

After this preparation PR is merged, check out that exact clean merged baseline and run
`PYTHONPATH=. python3 scripts/create_d5_lock.py --output D5_LOCK.json`. The generator
refuses dirty evaluation-critical files. Commit only the generated lock in a later
lock-only commit. `--verify D5_LOCK.json` accepts that descendant commit because it
checks ancestry and the locked file contents rather than requiring the lock commit to
be the baseline itself. Any drift in fixtures, agent/backend, scorer, runner, job
configuration, prompts/descriptors, or schedule blocks execution.

## Staged execution

The default runner is a network-free preflight. Live use later requires `--backend
live`, `--confirm-live`, `--baseline-lock`, a job/output, `OPENROUTER_API_KEY`, and a
positive bounded `--max-new-runs` value. The first invocation must use
`--max-new-runs 1`. Inspect the retained trial, complete evidence, immutable job
manifest, and incomplete validation output. Then resume from the identical lock and
output directory with a bounded continuation count. Completed model responses are
never rerun. An automatic scoring failure is valid experimental evidence of model
behaviour: it is retained and the bounded batch continues to later scheduled trials.
Lock, configuration, schedule, and live-message protocol defects fail locally before
the provider is called. Transport, authentication, provider/HTTP, or unusable paid
response failures are recorded and stop the current command immediately with a nonzero
status. Only a genuine unresolved pre-response transport failure may be retried later.

Cases remain sequential. “Parallel” means independent tool calls inside one ReAct
turn. A fresh agent and temporary decision log are used per trial. Live `max_steps` is
8: current parallel scripted evidence has a maximum of 6 model calls, providing a
controlled two-turn margin.

The six judged cases receive one queue item per case, not one per trial. Required
reviews remain pending until a reviewer supplies a substantive note. Final rates
combine recomputed code checks and those reviews. Cost is provider-measured, calculated
from dated configured pricing, or `null`; unavailable cost evidence cannot be finally
validated or aggregated. D4's scripted 100% is a regression baseline, never a live score.

## Exact operator runbook

Required order: **preparation PR merged → clean merged `main` checked out → lock
generated → lock-only commit merged → one-run smoke test → validation → bounded
continuation → human review → final validation → aggregation**.

Every member must privately set `OPENROUTER_API_KEY` in their own environment using
their own key. Never paste its value into a command, result, notebook, chat, or Git file.

```bash
# Zero-network preflight
python3 scripts/run_d5_live.py

# On clean merged main: generate, verify, then submit D5_LOCK.json as a lock-only commit
PYTHONPATH=. python3 scripts/create_d5_lock.py --output D5_LOCK.json
PYTHONPATH=. python3 scripts/create_d5_lock.py --verify D5_LOCK.json
git add D5_LOCK.json && git commit -m "Lock D5 evaluation baseline"
```

After the lock-only commit is merged, each assigned member runs only their job. The
first retained trial is always one run:

```bash
# Job 1 — TU WEIKANG
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 1 --output results/d5/job1-tu-weikang --max-new-runs 1
python3 scripts/validate_d5_results.py results/d5/job1-tu-weikang --lock D5_LOCK.json --allow-incomplete
# Job 2 — CHEN KE
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 2 --output results/d5/job2-chen-ke --max-new-runs 1
python3 scripts/validate_d5_results.py results/d5/job2-chen-ke --lock D5_LOCK.json --allow-incomplete
# Job 3 — KANG XINGYAO
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 3 --output results/d5/job3-kang-xingyao --max-new-runs 1
python3 scripts/validate_d5_results.py results/d5/job3-kang-xingyao --lock D5_LOCK.json --allow-incomplete
# Job 4 — YAO FANGXUAN
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 4 --output results/d5/job4-yao-fangxuan --max-new-runs 1
python3 scripts/validate_d5_results.py results/d5/job4-yao-fangxuan --lock D5_LOCK.json --allow-incomplete
# Job 5 — HUANG YIHAN
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 5 --output results/d5/job5-huang-yihan --max-new-runs 1
python3 scripts/validate_d5_results.py results/d5/job5-huang-yihan --lock D5_LOCK.json --allow-incomplete
```

Only after inspecting each retained smoke result, resume its same directory with a
bounded continuation (69 is the maximum remaining after one successful response).

An optional five-case burn-in can first add four trials. All four are retained even if
one or more model answers fail automatic scoring; those failures are part of the model
evaluation. Afterward, inspect whether failures are ordinary case-specific model errors
or a suspicious identical execution pattern before starting the remaining trials:

```bash
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 1 --output results/d5/job1-tu-weikang --max-new-runs 4
```

After the smoke or burn-in is reviewed, continue the remaining scheduled trials:

```bash
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 1 --output results/d5/job1-tu-weikang --max-new-runs 69
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 2 --output results/d5/job2-chen-ke --max-new-runs 69
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 3 --output results/d5/job3-kang-xingyao --max-new-runs 69
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 4 --output results/d5/job4-yao-fangxuan --max-new-runs 69
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 5 --output results/d5/job5-huang-yihan --max-new-runs 69
```

Normal resume skips every run ID already written, including transport failures and
paid malformed responses. A genuine pre-response transport failure may be retried only
deliberately; this can incur another charge and must target one failed stable ID:

```bash
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 1 --output results/d5/job1-tu-weikang --max-new-runs 1 --retry-run-id d4-clm-8842-t1
```

Never use `--retry-run-id` for a paid/model response; the runner refuses it. Substitute
the assigned job, directory, and audited failed run ID only after reviewing its row.

For each directory, a human must truthfully review all six entries in
`human_review_annotations.json`, changing `status` to `approved` or `rejected` and
supplying their own nonblank `reviewer` and substantive `review_note`. Never bulk-copy
D4 annotations or invent reviews. Then refresh the summary with a bounded resume command
(the runner makes no request when all stable run IDs are complete), perform final
validation, and aggregate:

```bash
# Exact zero-request summary refresh after all 70 run IDs are present:
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 1 --output results/d5/job1-tu-weikang --max-new-runs 1
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 2 --output results/d5/job2-chen-ke --max-new-runs 1
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 3 --output results/d5/job3-kang-xingyao --max-new-runs 1
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 4 --output results/d5/job4-yao-fangxuan --max-new-runs 1
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job 5 --output results/d5/job5-huang-yihan --max-new-runs 1

python3 scripts/validate_d5_results.py results/d5/job1-tu-weikang --lock D5_LOCK.json
python3 scripts/validate_d5_results.py results/d5/job2-chen-ke --lock D5_LOCK.json
python3 scripts/validate_d5_results.py results/d5/job3-kang-xingyao --lock D5_LOCK.json
python3 scripts/validate_d5_results.py results/d5/job4-yao-fangxuan --lock D5_LOCK.json
python3 scripts/validate_d5_results.py results/d5/job5-huang-yihan --lock D5_LOCK.json
python3 scripts/aggregate_d5_results.py --lock D5_LOCK.json results/d5/job1-tu-weikang results/d5/job2-chen-ke results/d5/job3-kang-xingyao results/d5/job4-yao-fangxuan results/d5/job5-huang-yihan
```

The shared `max_tokens=4096` ceiling is identical across models. It is above the
largest observed scripted response estimate (1,504 tokens) with more than 2.7× headroom while still
bounding spend. The per-run ceiling is US$0.035 and the cumulative job ceiling is
US$2.50: 70 runs at the per-run ceiling cannot be started past the job cap, which stays
below the teacher's US$3 member limit. These are safety ceilings, not invented provider
price or cost estimates; provider-measured usage and cost remain mandatory.

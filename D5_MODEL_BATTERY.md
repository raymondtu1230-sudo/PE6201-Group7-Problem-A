# D5 live-model battery

**Status, 6 September 2026: job 1 r6 complete; jobs 2–5 pending.**
Job 1 has 70 retained trials and six human-confirmed judgements; final success is
33/70 and recorded cost is USD 0.73754105. Its canonical path is
`results/d5/job1-tu-weikang-r6`. Earlier r3/r5 paths are audit-only pilots.

**Hold new paid jobs.** The current request supplies both `temperature` and
`top_p`, which conflicts with the documented Haiku 4.5 contract. The current
preflight misses this constraint. See [D5_REQUIREMENTS_CHECK.md](D5_REQUIREMENTS_CHECK.md)
for the offline reproduction, evidence and conditions for resuming. Live command
examples below are historical reference, not authorization to start a pending job.

## Two-stage baseline lock

The existing released baseline is `7e1657220534de48d48fa1c639ee75903469204b`,
with lock-only release `bad40060c0ba77b214de3317ca16e8b12a0700ec`. A new member
verifies the existing lock; they do not regenerate it just to start their job.
The following describes the release procedure only when a baseline actually changes.
After a runtime preparation PR is merged, check out that exact clean merged baseline and run
`PYTHONPATH=. python3 scripts/create_d5_lock.py --output D5_LOCK.json`. The generator
refuses dirty evaluation-critical files. Commit only the generated lock in a later
lock-only commit. `--verify D5_LOCK.json` accepts that descendant commit because it
checks ancestry and the locked file contents rather than requiring the lock commit to
be the baseline itself. Any drift in fixtures, agent/backend, scorer, runner, job
configuration, prompts/descriptors, or schedule blocks execution.

## Staged execution

The default runner prints the planned battery dimensions only; it does not verify the
lock. Use `--preflight` with a job, output and baseline lock for the actual keyless,
read-only validation. Live use later requires `--backend
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
Hitting either the per-run or job spending cap also stops the current command, after
retaining any billed attempt. The cap uses returned usage: a request already in flight
may cross the per-run threshold, so it is a stop threshold, not a provider-enforced
guarantee on the final charge.

Malformed model text is retained verbatim in the trace and scored as a model failure.
A judged case without a decision record remains a failed, reviewable result; an absent
reason does not invalidate the entire battery. Reviews cannot turn a code failure into
a pass. The public decision contract declares the routing rules, trigger codes and
missing-item formats for all models; the answer key is never included in model input.

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
On a shared terminal, clear the preceding member's environment variable and enter the
current member's key again using a hidden prompt. An existing variable or a manifest
member name does not establish key ownership. Each member runs all 50 cases / 70 trials;
the separate seven-case authoring blocks do not partition the D5 evaluation schedule.

```bash
# Zero-network plan display (not a lock check)
python3 scripts/run_d5_live.py

# On clean merged main: generate, verify, then submit D5_LOCK.json as a lock-only commit
PYTHONPATH=. python3 scripts/create_d5_lock.py --output D5_LOCK.json
PYTHONPATH=. python3 scripts/create_d5_lock.py --verify D5_LOCK.json
git add D5_LOCK.json && git commit -m "Lock D5 evaluation baseline"
```

After the lock-only commit is merged, each assigned member runs only their job. The
first retained trial is always one run:

Before entering an API key, run the actual preflight against the intended directory
(use a new directory for a changed baseline, and keep earlier paid evidence):

```bash
env -u OPENROUTER_API_KEY python3 scripts/run_d5_live.py --preflight --job 1 --output results/d5/job1-tu-weikang-r5 --baseline-lock D5_LOCK.json --max-new-runs 1
```

It validates the lock, schema, message roles, configuration, schedule and any existing
job/result identity without constructing an agent or creating output files. All later
commands must use that same chosen output directory; the paths below are examples for
the five job identities, not instructions to reuse an obsolete baseline's results.

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

## Team safety audit and recovery

See `D5_TEAM_READINESS.md` for the team-wide offline acceptance matrix. The live
entry now enforces the same strict result validation as `--preflight`, under an
exclusive operating-system lock for the output directory. A second runner fails
before making a model call. Reserved output paths and actual write/fsync access are
checked before spending. Never run two different directories for the same scheduled
job: a directory lock cannot detect separate copies on separate machines.

`active_trial.json` durably records each request's model input and each returned raw
text, usage, response identifier and termination reason. It contains no Authorization
header. Ordinary malformed actions remain scored model failures and the batch continues.
Provider errors embedded in HTTP 200 stop the batch and retain their partial evidence.
The checkpoint is removed only after the scored trial and derived files are saved.

An interrupted or unprocessed checkpoint blocks further paid execution. Do not delete
it or rerun the case to make it disappear. If the checkpoint already contains a scored
row, this keyless command restores the row and summaries without calling a model:

```bash
python3 scripts/run_d5_live.py --recover --job 1 --output YOUR_EXISTING_OUTPUT --baseline-lock D5_LOCK.json
```

For an in-flight or unscored response, recovery refuses automatic replay: retain the
journal, inspect the response and reconcile any uncertain provider charge offline.
`known_cost_usd` is the measured lower bound already returned; `cost_usd=null` or
`billing_complete=false` means the complete bill is unresolved. Further paid execution
is blocked until that evidence is reviewed and reconciled. Unknown charges are never
silently entered as zero. An operating-system kill or loss of the storage device cannot
be made transactional with a remote provider; preserve the pre-request checkpoint.

Generation settings are shared requested settings. Providers may ignore parameters
their model does not support; do not claim identical effective sampling solely because
the request includes `temperature=0`. Inspect actual model identity and termination
metadata in each member's smoke trace. Do not alter one member's prompt, limits or
settings after seeing their score. A public model listing or successful key-auth check
does not guarantee generation access, available balance, output quality or uptime.

The historical safety repair changed locked runtime files and was released through
PRs #24/#25. It is already merged; do not repeat that lock-generation procedure
merely because the next member joins.
Existing r3/r5 pilot files retain their original baseline and cost evidence; do not
rewrite their hashes or silently mix them into results from the repaired baseline.

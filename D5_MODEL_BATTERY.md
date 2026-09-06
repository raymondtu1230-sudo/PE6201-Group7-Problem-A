# D5 live-model battery: current operating sequence

Updated 6 September 2026. The interface audit and decision record are in
[D5_CROSS_MODEL_CHECK.md](D5_CROSS_MODEL_CHECK.md). This sequence replaces the old
r3/r5 examples; those results remain historical evidence, not continuation targets.

## Retained GPT and pending jobs

TU WEIKANG's r6 remains at `results/d5/job1-tu-weikang-r6`: 70 trials, 33 final
passes / 37 failures, USD 0.73754105, six confirmed reviews. Keep its original lock,
manifest and data. No paid GPT rerun is currently authorized. All five jobs have
full offline rehearsals, including GPT if a later collection becomes necessary.
The user selected retention with explicit version/settings disclosure; this is
not instructor approval of the deviation from the same-commit D5(b) requirement.

| Job | Member | Model | Prompt | New collection directory |
| --- | --- | --- | --- | --- |
| 1 | TU WEIKANG | `openai/gpt-5-mini` | v2 | `results/d5/job1-tu-weikang-r7` — reserved, only if a new collection is later authorized |
| 2 | CHEN KE | `qwen/qwen3-30b-a3b-instruct-2507` | v2 | `results/d5/job2-chen-ke-r7` |
| 3 | KANG XINGYAO | `anthropic/claude-haiku-4.5` | v2 | `results/d5/job3-kang-xingyao-r7` |
| 4 | YAO FANGXUAN | `google/gemini-2.5-flash-lite` | v2 | `results/d5/job4-yao-fangxuan-r7` |
| 5 | HUANG YIHAN | `google/gemini-2.5-flash-lite` | v1 | `results/d5/job5-huang-yihan-r7` |

Each job runs the same 50 cases: 40 ordinary trials plus 10 negative cases repeated
three times, totalling 70 trials. The seven-case authoring assignments do not divide
this schedule. Fixed requested settings are temperature=0 and max_tokens=4096,
with no top_p. The maximum is 8 agent steps. Requested sampling settings need not
be equally effective across providers; see the audit's interface limitations.

## Release and local state

The runtime/audit PR is merged first. A maintainer then uses a clean checkout of
that exact merged commit to generate the lock and publishes only `D5_LOCK.json`
in a separate PR. The lock records the baseline, critical file hashes, prompts and
schedule. Never edit hashes or regenerate a lock just to make a member's checkout
pass. A documentation-only or lock-only descendant can verify against the baseline.

Only the release maintainer runs generation, from the clean merged baseline:

```bash
python3 scripts/create_d5_lock.py --output D5_LOCK.json
python3 scripts/create_d5_lock.py --verify D5_LOCK.json
```

The runtime PR alone is not a paid release: the old lock must reject it until the
separate replacement lock is merged. After release, members verify the committed
lock. They do not generate their own locks or use a temporary test lock.

The assistant's checkout is separate from a member's Codespaces. Give the operator
one command group at a time and wait for the complete output. The first group is
exactly:

```bash
git status --short --branch
```

Inspect local changes before any synchronization. Preserve every result and local
edit; do not use `git reset --hard`. On a confirmed clean checkout, synchronize
`main` with a fast-forward pull, then inspect the full HEAD and verify the lock:

```bash
git rev-parse HEAD
python3 scripts/create_d5_lock.py --verify D5_LOCK.json
```

Compare the baseline and lock hash with the merged lock-only PR. Confirm that the
member's selected new directory is unused before the first trial. Subsequent stages
must use that same directory and immutable manifest. Do not create a different
copy on another machine to run the same job concurrently.

## Keyless checks and private key entry

For the current member, select the exact job/directory from the table. This example
is the first cohort member, Haiku; it is not authorization to start paid execution:

```bash
D5_JOB=3
D5_OUTPUT=results/d5/job3-kang-xingyao-r7
python3 scripts/run_d5_live.py --preflight --job "$D5_JOB" --output "$D5_OUTPUT" --baseline-lock D5_LOCK.json --max-new-runs 1
```

Preflight is keyless, read-only and zero-network. It checks the real lock, schedule,
settings, dialogue contract and existing output; it does not prove account credit,
model access or provider availability. For an empty directory it must show zero
completed and 70 pending trials. A plan-only run without `--preflight` is not this
verification. No real result directory is created by the release audit.

Before paid execution, the current member privately checks their account balance
and earlier D5 charges. Each member uses their own key. A manifest's member name
and an existing environment variable cannot establish who owns a key. On a shared
terminal clear the previous member's variable, then use a hidden input:

```bash
unset OPENROUTER_API_KEY
read -r -s -p 'Current member OpenRouter key: ' OPENROUTER_API_KEY
export OPENROUTER_API_KEY
```

Never paste a key into chat, Git, notebooks or literal shell commands, and never
print the variable. Switch member, job, directory and key together; do not run a
multi-model shell loop using one member's key. Clear the variable when finished.

## Cohort checkpoints: 1, then 4, then 65

The pending cohort order is Haiku (job 3), Qwen (job 2), Gemini v2 (job 4), Gemini
v1 (job 5). Complete and inspect the first trial of **every** pending job before
any job adds four. Complete and inspect all four five-trial sets before **any**
job starts its remaining 65. If GPT is later newly authorized, put it through the
same checkpoints under the released lock. Do not automatically restart r6.

Only after the current member's environment/key/budget checks and authorization,
run the first scheduled trial:

```bash
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job "$D5_JOB" --output "$D5_OUTPUT" --max-new-runs 1
python3 scripts/validate_d5_results.py "$D5_OUTPUT" --lock D5_LOCK.json --allow-incomplete
```

Read the complete retained trace, manifest, trial and summary. Confirm the assigned
model/prompt, actual assistant/Observation history, finished actions, provider
response IDs, token usage and complete measured billing. Distinguish a model's
wrong answer from a missing/misrepresented tool observation. A passing score is
not required to pass this integration checkpoint; a protocol or billing problem
must be resolved before continuing. Keep the failed response and its cost.

After the first-trial checkpoint passes for the whole cohort, each member can
append four in their own unchanged directory:

```bash
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job "$D5_JOB" --output "$D5_OUTPUT" --max-new-runs 4
python3 scripts/validate_d5_results.py "$D5_OUTPUT" --lock D5_LOCK.json --allow-incomplete
```

Inspect all five traces and measured costs for every job. Estimate remaining spend
using observed calls/tokens and costly cases, not only a cheap first trial. Five
ordinary cases do not cover all negative cases or later failures. If the available
budget cannot support continuation, pause and record that limitation instead of
raising limits or opening a fresh directory.

Only after the whole cohort's five-trial checkpoint is reviewed, continue each job:

```bash
python3 scripts/run_d5_live.py --backend live --confirm-live --baseline-lock D5_LOCK.json --job "$D5_JOB" --output "$D5_OUTPUT" --max-new-runs 65
python3 scripts/validate_d5_results.py "$D5_OUTPUT" --lock D5_LOCK.json --allow-incomplete
```

The first five are part of the official 70 when the version remains unchanged;
they are not extra trials. If a necessary repair changes the experiment, assess
its impact and version consequences before making the change or spending again.

## Failures, costs and recovery

| Observation | Required action |
| --- | --- |
| Wrong answer, refusal, malformed model text, or repeated action with correctly supplied history | Preserve and score the failure; continue. Never tune code/prompts to improve the observed score. |
| Empty answer with explicit filtering/output-limit/refusal evidence and complete billing | Preserve finish reason, refusal text and charge; score failure and continue. No fabricated answer or automatic retry. |
| Network, authentication, explicit provider error, unknown empty response, malformed protocol or missing billing | Preserve evidence and known charges; stop the job and determine a safe recovery. |
| Incorrect scoring or summary logic | Recompute offline from sufficient original traces; do not call the model again to fix a report. |
| Runtime defect that changed supplied information or execution opportunities | List affected records, proposed repair and comparability consequences before modifying or recollecting. |

The per-trial USD 0.08 and per-directory job USD 2.80 values are stopping thresholds,
not account hard caps. An in-flight request can cross a threshold. The runner
requires room for the full next trial allowance before starting it; reaching a
cap is not a reason to change directories. Preserve earlier pilot charges as part
of personal D5 spending. TU WEIKANG's archived r3/r5/r6 total is about USD 0.81427205,
excluding other coursework. Actual remaining account balances are not known here.

`active_trial.json` checkpoints requests and returned evidence before further calls.
A disk failure or interruption can leave an unresolved checkpoint. Keep it: deleting
it can erase evidence of a paid request. The recovery command is keyless:

```bash
python3 scripts/run_d5_live.py --recover --job "$D5_JOB" --output "$D5_OUTPUT" --baseline-lock D5_LOCK.json
```

Recovery only restores an already-scored row that failed to append. It does not
replay an ambiguous request. An unresolved request requires offline billing/evidence
reconciliation. Completed model/provider responses cannot be retried. A permitted
transport retry is considered only after the original charge is known and the
resume command has been specifically reviewed; there is no automatic retry loop.
An output-directory process lock prevents a second writer in that directory, but
cannot detect duplicated jobs in different directories or different machines.

## Review and final comparison

Six judged cases need truthful review annotations with substantive notes, one per
case. Pending reviews are not passes. Reviews cannot override failed code checks.
Test-fixture annotations in the simulations are not human reviews or experiment
results. There is no paid judge model in this plan.

After all 70 completed run IDs are already present and the required annotations
are added, an invocation with `--max-new-runs 1` refreshes the summary without new
model calls. Verify all 70 are present before using that procedure. Run final
validation without `--allow-incomplete`:

```bash
python3 scripts/validate_d5_results.py "$D5_OUTPUT" --lock D5_LOCK.json
```

Aggregate only complete new-lock directories with the existing strict aggregator.
Do not pass r6 to the new lock, rewrite its manifest, or weaken the validator.
For the selected retained-GPT route, validate r6 in a separate historical checkout
using its original release and lock; put its metrics beside the new results in a
clearly labelled baseline/settings comparison table. State the same-commit deviation.
If a new GPT run is later authorized and completed, it can join the same-lock
aggregation while r6 remains separately preserved. D6 analysis, D7's two free
fault-injection demonstrations, final report and video still require completion.

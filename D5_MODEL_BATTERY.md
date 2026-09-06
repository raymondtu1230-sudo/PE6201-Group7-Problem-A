# D5 live-model battery: current operating sequence

Updated 6 September 2026. The interface audit and evidence are in
[D5_CROSS_MODEL_CHECK.md](D5_CROSS_MODEL_CHECK.md). This sequence replaces the old
r3/r5 examples; those results remain historical evidence, not continuation targets.

## Five new collections on one version

All five jobs below will collect new results under the published lock and one
exact checkout commit. Each job is still pending. TU WEIKANG's r6 remains at
`results/d5/job1-tu-weikang-r6` as a completed historical collection, with its
original manifest, 70 responses and six confirmed reviews. The
[result index](results/d5/README.md) explains its role and separate costs.
The final comparison will use the new GPT run regardless of whether it scores
higher or lower than r6.

| Job | Member | Model | Prompt | New collection directory |
| --- | --- | --- | --- | --- |
| 1 | TU WEIKANG | `openai/gpt-5-mini` | v2 | `results/d5/job1-tu-weikang-r7` |
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

PR #31 merged the runtime/interface audit; PR #32 independently published
`D5_LOCK.json`. The published values are:

- Runtime baseline: `1dc27cfbe257901c8e38243acb420f154a1d5664`.
- Lock hash: `146704d01e9b4105fcdee2efa7b01c329624b8bd2415b9b09cab0832fad639a0`.

The lock covers all critical code, configuration, data, prompts and the schedule.
This preparation changes documentation and evidence only, so the published lock
continues to apply. Members verify this lock; they do not generate another one.

The maintainer's release handoff supplies the **full merge SHA of the preparation
PR**. That is the common checkout commit for all five jobs. A lock verifies runtime
identity but permits documentation-only descendants; it does not by itself prove
that every member checked out the same HEAD. Record and compare the full HEAD
separately. Freeze that chosen commit throughout the cohort, including resumptions;
do not pull a moving `main` between members or stages.

The assistant's checkout is separate from a member's Codespaces. Give the operator
one command group at a time and wait for the complete output. The first group is
exactly:

```bash
git status --short --branch
```

Inspect local changes before any synchronization. Preserve every result and local
edit; do not use `git reset --hard`. After reviewing the output, fetch the repository
and check out the exact handoff commit in detached mode, or use a separate clean
worktree if existing work must remain in place. The maintainer supplies that command
with the actual SHA after the status check. Then inspect HEAD and verify the lock:

```bash
git rev-parse HEAD
python3 scripts/create_d5_lock.py --verify D5_LOCK.json
```

Compare HEAD with the common handoff SHA and the baseline/hash with the values
above. Save this keyless verification output with the member's execution evidence;
the runtime manifest records the baseline, not a separate checkout SHA. Confirm that the
member's selected new directory is unused before the first trial. Subsequent stages
must use that same directory and immutable manifest. Do not create a different
copy on another machine to run the same job concurrently.

## Keyless checks and private key entry

The release-preparation evidence is in
[`results/d5-readiness/start_preparation.json`](results/d5-readiness/start_preparation.json).
It binds the existing five-job simulation evidence to the unchanged runtime,
checks the published lock and all five unused output paths, and checks the
offline summary-refresh command. It is not a member's Codespaces or account check.

For the current member, select the exact job/directory from the table. This example
is the first cohort member, Haiku; it is not authorization to start paid execution:

```bash
D5_JOB=3
D5_OUTPUT=results/d5/job3-kang-xingyao-r7
python3 scripts/run_d5_live.py --preflight --job "$D5_JOB" --output "$D5_OUTPUT" --baseline-lock D5_LOCK.json --max-new-runs 1
```

Preflight is keyless, read-only and zero-network. It checks the real lock, schedule,
settings, dialogue contract and existing output; it does not prove account credit,
model access or provider availability. For an unused directory it must show
`existing_attempts=0` and `remaining_unattempted_trials=70`.
A plan-only run without `--preflight` is not this
verification. No real result directory is created by the release audit.

Before paid execution, the current member privately checks their account balance,
key allowance and earlier D5/course charges using their own OpenRouter account or
the read-only `/api/v1/key` endpoint. A null key limit is not an unlimited account
balance. Record only member, available amount, earlier spending and check time;
never the key. Use the [budget references](D5_BUDGET_PLAN.md) to assess headroom.
Each member uses their own key. A manifest's member name
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

The cohort order is Haiku (job 3), Qwen (job 2), Gemini v2 (job 4), Gemini v1
(job 5), GPT (job 1). Complete and inspect the first trial of **all five jobs**
before any job adds four. Complete and inspect **all five five-trial sets** before
any job starts its remaining 65. Finish the other four remaining batches before
GPT's remaining 65. The new GPT job uses `r7`; r6 is never a continuation target.

These are separate reviewed command groups, not a script to run from top to
bottom. The runner enforces the first single trial and the supplied batch limit;
it cannot know whether other members' separate machines passed a cohort checkpoint.
The maintainer must check every member's retained evidence before advancing a stage.
Recheck the exact HEAD, lock, same job/output and available budget before each stage.

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

Six judged cases in each new job need truthful review annotations with substantive
notes, one per case. New GPT outputs require new review; do not copy r6's approvals
or rejections. Pending reviews are not passes. Reviews cannot override failed code checks.
Test-fixture annotations in the simulations are not human reviews or experiment
results. There is no paid judge model in this plan.

Stop all runners before editing annotations. After all 70 completed model responses
are present and annotations are added, a maintainer can refresh derived files
**offline**, with no live runner entry. The command uses the existing directory
lock and rejects unresolved request checkpoints:

```bash
python3 - "$D5_OUTPUT" <<'PY'
import json
import sys
from pathlib import Path
from scripts.d5_safety import ACTIVE, exclusive_output
from scripts.run_d5_live import load_labels, rebuild_reviews, write_summary
from scripts.validate_d5_results import validate
output = Path(sys.argv[1])
if not output.is_dir():
    raise ValueError('Expected an existing completed result directory')
with exclusive_output(output):
    if (output / ACTIVE).exists():
        raise ValueError('Resolve the retained request checkpoint before refresh')
    info = validate(output, Path('D5_LOCK.json'), allow_incomplete=True)
    rows = [json.loads(line) for line in (output / 'trials.jsonl').read_text().splitlines()]
    completed = {row['run_id'] for row in rows if row.get('transport_status') == 'model_response'}
    if len(completed) != 70 or not info['billing_complete']:
        raise ValueError('Collection or billing incomplete')
    labels, _ = load_labels()
    labels = {label['case_id']: label for label in labels}
    rebuild_reviews(output, rows, labels)
    write_summary(output, rows, labels)
PY
```

This preserves original responses and existing annotations. Run final validation
without `--allow-incomplete`; it rejects missing reviews or incomplete billing:

```bash
python3 scripts/validate_d5_results.py "$D5_OUTPUT" --lock D5_LOCK.json
```

After each of the five new directories passes final validation, run the explicit
five-directory aggregation. Do not use a wildcard that could include historical
results or omit a missing member:

```bash
python3 scripts/aggregate_d5_results.py --lock D5_LOCK.json \
  results/d5/job1-tu-weikang-r7 \
  results/d5/job2-chen-ke-r7 \
  results/d5/job3-kang-xingyao-r7 \
  results/d5/job4-yao-fangxuan-r7 \
  results/d5/job5-huang-yihan-r7
```

The resulting formal comparison has four v2 model families and the fixed-Gemini
v1/v2 pair. Keep historical collection costs separately in the spending ledger.
D6 still needs dated list-price economics using measured tokens, with caching and
reasoning treatment explained; no price fallback is enabled in the live config,
so a missing provider bill stops instead of being replaced by an estimate.
D7's two free fault-injection demonstrations, final report, video, self-appraisal
and a matching repository/code ZIP still require completion.

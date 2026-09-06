# D5 team safety acceptance — 6 September 2026 (SGT)

**Current operating reference:** [D5_CROSS_MODEL_CHECK.md](D5_CROSS_MODEL_CHECK.md)
and [D5_MODEL_BATTERY.md](D5_MODEL_BATTERY.md) supersede this historical run order
with the five-job interface audit, r6 retention decision and cohort checkpoints.

**Historical repair audit.** For the later check of merged main, teacher-source
precedence, completed job 1 and the newly identified provider-parameter blocker,
read [D5_REQUIREMENTS_CHECK.md](D5_REQUIREMENTS_CHECK.md). Passing the synthetic
tests below does not certify every provider's generation-parameter contract.

This audit started from `main` commit `896f2ac4453f87719f7b5672c0a54e28603f0545`.
It used synthetic provider responses and removed real API keys. No live generation
or additional paid trial was performed. Temporary simulated scores and annotations
are test fixtures, not student experiment results or human reviews.

## Team and evaluation scope

The filled, signed `TEAM_DECLARATION(2).pdf` and `config/d5_jobs.json` agree:

| Job | Member | Model ID | Prompt |
|---|---|---|---|
| 1 | TU WEIKANG | `openai/gpt-5-mini` | v2 |
| 2 | CHEN KE | `qwen/qwen3-30b-a3b-instruct-2507` | v2 |
| 3 | KANG XINGYAO | `anthropic/claude-haiku-4.5` | v2 |
| 4 | YAO FANGXUAN | `google/gemini-2.5-flash-lite` | v2 |
| 5 | HUANG YIHAN | `google/gemini-2.5-flash-lite` | v1 comparison |

Each member uses their own key. Each job runs the same 50 cases and 70 scheduled
trials: 40 ordinary cases once, 10 negative cases three times. The seven-case
authoring blocks are separate responsibilities, not separate evaluation subsets.
The maintainer may integrate the members' genuine submitted evidence into GitHub.

Requirement precedence: the revised assignment/FAQ, 1 September document update
and newer 50+ case announcement govern conflicting older case counts. Teacher
requirements are distinct from the student-filled declaration and student terminal
traces. The D5 comparison requires common fixtures, schedule, locked code and v2
prompt, with the declared fixed-model v1 comparison as the explicit exception.

## Reproduced gaps and fixes

| Previously reproduced failure | Corrected behavior |
|---|---|
| An array-valued tool name raised TypeError before saving the paid trial | Validate action types; retain a scored malformed-action failure and continue the schedule |
| HTTP 200 with provider error and partial text looked like a normal answer | Recognize top-level/choice errors and error finish reasons; retain partial text, usage and error metadata; stop the batch |
| Finish reasons were discarded | Retain normalized and native termination reasons, including length truncation; no score-dependent limit changes |
| Direct live entry skipped strict result validation | Apply the same preflight inside the paid entry, again under the output lock |
| Two runners could purchase the same next trial | Use a nonblocking OS file lock; a second writer makes zero provider requests |
| Invalid output targets were discovered after spending | Check reserved path types and probe actual write/fsync access before calling the provider |
| Interrupts or parsing/program errors lost returned-call evidence | Flush a request/response journal before continuing; unresolved journals block automatic replay |
| Trial/summary writes could fail after model completion | Keep the scored row in the journal; keyless recovery restores a complete checkpoint without another provider call |
| Missing usage hid earlier known costs | Retain the measured lower bound separately; unresolved billing blocks further paid execution |
| A generation-settings object could override the selected model/messages | Validate the permitted settings and finite positive limits before the provider boundary |

The common system instruction, descriptors, decision contract, evaluation fixtures,
schedule, model assignments and requested sampling settings were not changed to improve
scores. Ordinary model failures still count and do not stop the batch.

## Offline acceptance

Final full suite: **138 tests passed** in 110.208 seconds, including **15 team-safety
tests** and the following independent scenarios. The network guard reported
`network_attempts=0` and `paid_model_calls=0`.

- All five jobs complete staged `1 + 4 + 65` lifecycles through actual HTTP message
  serialization: 350 scheduled simulated trials, correct model/prompt/key routing,
  six synthetic review entries per job, fixed-model comparison and aggregation.
- **60 late-failure scenarios**: five jobs × positions 6/35/70 × malformed tool type,
  malformed JSON, provider error and HTTP 429. Model failures continue to 70;
  infrastructure failures stop at the injected trial and retain evidence.
- HTTP 400/401/402/403/408/429/500/502/503 and timeout after earlier returned calls:
  stop, preserve measured costs and block spending against uncertain billing.
- HTTP-success error envelopes, length metadata, missing usage, keyboard interruption,
  an unexpected program exception, result append failure, derived-summary failure,
  same-directory exclusion, corrupt stored scores/identity/traces and invalid paths.

Run the complete gate with:

```bash
python3 scripts/check_d5_readiness.py
```

It removes the real key, prohibits Python network connections (including subprocess
Python entry points), runs the full suite and stops the test process at 300 seconds.
Its final JSON reports test validity and the number of attempted network connections.
Separate deterministic regressions also passed: D2 v1/v2 and sequential/parallel
each 70/70; D3 both descriptor versions 15/15; D4 code scoring 70/70. No human review
was fabricated. Compile and whitespace checks passed. D0–D4 artifacts were preserved.

## Release and honest limits

The current tracked lock predates these runtime changes and must reject the new code.
Merge the repair first, generate a lock from clean merged main, then merge the lock-only
change. Never bypass this gate or rewrite the hashes on already-paid results. Preserve
the earlier five r5 trials with their original version and cost provenance; they are
pilot evidence, not interchangeable with a newly locked formal battery.

This is a tested software-readiness claim, not a guarantee of live model accuracy,
provider availability, account access, balance or zero future charges. A returned cost
cap is a stopping threshold, not an upper bound on a request already in flight. Set
personal provider-account limits privately if a hard spending limit is needed.
The directory lock cannot prevent duplicate jobs in different directories/machines.
Use one designated output per job and explicitly enter the assigned member's own key.

An HTTP auth check does not prove model-generation access. Supported parameters may
differ: shared requested temperature/top-p values do not establish identical effective
sampling. Inspect each model's actual response metadata at its controlled smoke stage.
See OpenRouter's [error response documentation](https://openrouter.ai/docs/api_reference/errors-and-debugging)
and [provider parameter routing](https://openrouter.ai/docs/guides/routing/provider-selection).

If a request is interrupted before its response is durably received, keep the journal
and reconcile the provider charge. No automatic retry is safe when the first charge is
uncertain. Storage loss or an operating-system kill cannot be made transactional with
a remote paid API. Completed checkpoints can be recovered with the keyless command
documented in `D5_MODEL_BATTERY.md`; ambiguous checkpoints require an offline audit.

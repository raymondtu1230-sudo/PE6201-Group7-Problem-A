# D5 audit and zero-cost rehearsal — 5 September 2026

**Historical audit:** the commits, test totals, locks and next steps below describe
5 September. For the current published lock, all-five-job checks and designated
new result directories, use [D5_MODEL_BATTERY.md](D5_MODEL_BATTERY.md) and
[D5_CROSS_MODEL_CHECK.md](D5_CROSS_MODEL_CHECK.md).

Reviewed main: `6dfc2dc290f9b5b23b84da1d9da4afcba586429f`.
Its lock verified with hash `87d0832519035858e6910f456895350428234f44fe6ae3bfb9dcee87b19f1309`.
The previous 115 tests passed with socket connections blocked. That did not cover
all failure paths through final validation. No OpenRouter request was made in this audit.

## Teacher-source precedence

Read the revised A2 brief, revised FAQ, Document Updates (1 September), Adding Extra
Cases guide, self-appraisal requirements, and later teacher announcements supplied
as `Professor's-Requirements.txt` and `scaffold.txt`. The later announcement says
"recommended is total of 50+" and "35+ on top of what i provided". It supersedes the
older 30–50 range. Retain the existing 15 shipped plus 35 added cases; do not call 50
the latest permitted maximum. With 10 negatives, 40 single trials plus 30 negative
trials remains the declared 70-trial schedule.

The five jobs implement four different v2 model families and one fixed-model Gemini
v1 comparison. The v1 job is the explicit exception to identical v2 across models.
Each member must actually run their assigned job on their own key and contribute
evaluation cases. A job manifest or planned ownership row alone cannot prove this.
Price-tier labels are planning labels; dated pricing and measured costs remain D5/D6
evidence to collect. The default code and D3/D7 reproduction must remain free.

## Reproduced gaps and changes

| Gap in reviewed main | Reproduction | Change |
| --- | --- | --- |
| Plain text without Action/Final leaves an empty trace | Mock HTTP returns `I cannot complete this request.`; validation raises `incomplete trace` | Retain original malformed response; score failure and continue |
| Judged case without a record cannot validate | Fail CLM-9029, finish 70 trials; validation raises `incomplete judgement queue evidence` | Allow an absent reason only when it matches the retained candidate; code failure remains failure |
| Negative-case output vocabulary is hidden | Public model input lacks the exact hostile trigger and the formats used by exact missing-item checks | Declare general routing rules, trigger values and missing-item formats for both v1/v2; never disclose case labels |
| A run hitting its spending cap does not stop the batch | Inject a 0.04-dollar mock call against the 0.035-dollar threshold during a four-trial continuation | Retain the billed failed trial, return nonzero and stop the current batch |
| Default “preflight” prints constants | It does not call lock/configuration validation | Add explicit keyless `--preflight` using the actual checks and read-only output identity validation |

Also correct the obsolete 50-case maximum and 14-case checklist wording, and remove
the suggestion that D2(c) needs another paid sequential/parallel battery. The teacher
requires that comparison to be measured; the existing scripted comparison provides
that evidence. D5 still requires the live v1/v2 pair and cross-model results.

## Verification

`tests/test_d5_audit_regressions.py` first reproduced five failures on the reviewed
main. With the changes, the full suite passes **123 tests**, with **0 attempted
socket connections**. Its HTTP simulator reads serialized message roles and tool
observations. It does not bypass `call_live_model` serialization.

- All five configured jobs: 70 simulated trials each, in stages 1 + 4 + 65.
- Positions 2, 3, 4, 5: malformed model answers continue; transport failures stop.
- A judged-case failure survives all 70 trials, simulated review and final validation;
  final pass rate is 69/70, not 100%. Test-only review annotations stay in temporary files.
- A deliberate return to flattened conversation history is rejected before transport.
- A spending-cap failure stops the batch; a corrupted lock fails keyless preflight.
- D2 v1/v2 and sequential/parallel: 70/70 each; descriptor guardrails: 15/15 each.
- D4: 70/70 with the existing six approved human annotations preserved.
- Fixture-integrity checker, Python compilation and whitespace checks pass.

The HTTP simulator uses deterministic planned responses to test program integration.
These are not live GPT, Claude, Qwen or Gemini results and must not be reported as
model accuracy. The shared prompt now includes previously missing contract rules,
so scripted input-token estimates were regenerated. Fixtures, answer keys, scoring
criteria and schedule remain unchanged.

## State after review

D0–D4 provide the build and offline evidence. The live descriptor comparison is still
pending, so do not describe all D2 evidence as final. D5 live results, D6 cost model,
D7 deletion-based failures, final report, video and completed contribution evidence
remain outstanding. The audit tests do not replace D7.

Any runtime/prompt change requires a new baseline lock before paid execution. Keep
old r3/r4 paid evidence separate. Use a fresh output path after the new lock is
merged and verified. The old main lock must fail against these changed runtime files.
No model scoring failure is retried to improve its grade, and no paid test was used
to discover or validate these fixes.

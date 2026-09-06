# D5 final risk check — 6 September 2026

This audit starts from the released PR #33 checkout
`7eda9537c1df1b433ed4bc1e24305fee0e193874`. It repeats the complete offline suite
and adds independently specified bad responses and monetary boundaries. It uses
synthetic keys and responses; no real model generation or account check occurs.
The [machine evidence](results/d5-readiness/final_risk_audit.json) records the
test outcomes and exact source hashes. The [runbook](D5_MODEL_BATTERY.md) is the
current execution reference. Earlier readiness reports remain historical snapshots.

Release follow-through: PR #34 merged these repairs; PR #35 published the
replacement lock. The common experimental checkout is
`4c79c92fd0e68d802e1c6390afa2427202d2aa21`. Subsequent documentation clarifications
leave the runtime, locked settings, recorded results and chosen checkout unchanged.

## Reproduced gaps and bounded repairs

| Gap missed by the original tests | Reproduction and new behavior |
| --- | --- |
| Per-trial incremental floating-point error | Two calls costing USD 0.016605 and 0.063395 total exactly USD 0.08. Previously their incremental float sum could reject the returned Final as over budget. Decimal comparisons now process that Final, forbid a further paid request at the boundary, and stop above it. Raw charges are unchanged. |
| Returned identity and message envelope unchecked for nonempty text | A response naming a different model was accepted as a normal result. Now a different returned model stops with its original identity and known cost; missing/invalid response ID, model ID or assistant role is a protocol failure. |
| Fractional token usage accepted | A usage value such as prompt_tokens=1.5 could be truncated in the derived row. Counts must now be finite, nonnegative integers; 12.0 is accepted, 1.5/bools/negative/string counts are rejected. A known finite charge remains recorded, and unresolved usage blocks further spending. |

Malformed records remain available for incomplete diagnostic validation. This does
not make them valid final submissions or authorize resumption. Explicit provider
errors retain their existing precedence. A model's wrong answer, malformed model
text, refusal or explicit output exhaustion remains a scored failure; it is not
automatically retried or turned into a passing answer.

The response-envelope fixtures follow the public gateway's normalized
[response contract](https://openrouter.ai/docs/api_reference/overview).
[Provider errors](https://openrouter.ai/docs/api_reference/errors-and-debugging)
can be carried in an HTTP-success response. Exact matching of the returned model
is our experiment-integrity rule: a provider alias or snapshot spelling difference
will stop for review too. We have not proven that all future routes return the
configured ID verbatim; no alias is silently substituted or relabelled.

## Five-job coverage

| Job | Fixed model / prompt | Final offline coverage | Real new-release status |
| --- | --- | --- | --- |
| 1, TU WEIKANG | OpenAI GPT-5 Mini / v2 | Full staged 70-trial simulation plus new boundary, identity, usage and long-history fixtures | Pending; historical r6 exists |
| 2, CHEN KE | Qwen3 30B A3B Instruct 2507 / v2 | Same coverage | Pending |
| 3, KANG XINGYAO | Claude Haiku 4.5 / v2 | Same coverage; temperature/top_p conflict rejected before transport | Pending |
| 4, YAO FANGXUAN | Gemini 2.5 Flash Lite / v2 | Same coverage | Pending |
| 5, HUANG YIHAN | Gemini 2.5 Flash Lite / v1 | Same coverage with declared v1 descriptors | Pending |

The new seven test methods include 30 late-fault scenarios: five jobs, faults
at trial 6/35/70, and either a wrong returned model or fractional usage. Each
scenario follows the real runner's 1 + 4 + 65 staging, retains the failed trial
and known charge, and stops at the injected fault. Invalid-usage resumption makes
no new call. These short synthetic answers exercise control flow, not model quality.

Additional checks cover the exact per-trial boundary and either side of it for
every job, malformed identities/roles, integral float counts, retained cache and
reasoning usage details, and seven complete assistant/Observation pairs with long
Unicode and untrusted narrative text. The latter checks serialization preservation;
it is not a measurement of a real provider's tokenizer, output sufficiency or cost.

The complete suite also includes the existing all-five-job staged 70-trial battery,
ordinary failures, later provider errors and over-budget charges, HTTP/authentication
failures, ambiguous interruptions, disk write failures, single-directory concurrency,
result validation, summary aggregation and no-call recovery. Simulated scores and
review labels are fixtures, not experiment results or human approvals.

Run the complete keyless, network-denied gate from the repository root:

```bash
python3 scripts/check_d5_readiness.py
```

The original 154-test suite passed before these added cases. Three newly selected
methods then reproduced the gaps with 25 failing subtests against the old code.
During repair, the expanded suite also caught a changed error-message prefix;
the original `unresolved billing` prefix was retained for compatibility. The final complete run passed **161 tests in 148.581 seconds**, with zero network
attempts and zero paid model calls. The full log is linked in the machine evidence.
The gate removes the real OpenRouter key, blocks Python network access and has
a 300-second timeout. No paid calls are used to obtain a passing test result.

## Effects on the experiment and earlier results

The four changed protected files are `src/claim_agent.py`, `src/live_backend.py`,
`scripts/run_d5_live.py` and `scripts/validate_d5_results.py`. This repairs stopping
and evidence validation. The outgoing request bodies match the earlier PR #31
wire audit; prompts/descriptors, model assignments, case data, answer key, scoring
logic, 8-step limit and USD 0.08/2.80 caps are unchanged. Synthetic HTTP fixtures
were updated to supply the documented identity and assistant-role fields.

All 16 retained r3/r5/r6 files match the PR #33 hashes. r6's 70 stored code checks
reproduce; all 359 stored provider response model IDs are the assigned GPT model,
their response IDs are nonempty, and stored token counts are integral. Its most
expensive trial is USD 0.02133245, below both the old and new trial caps. No effect
of these reproduced gaps was identified in those records. The old message role
was not stored in r6's response metadata, so this check does not claim to verify it
retroactively. Nothing here proves a new stochastic run would repeat r6's answers.

r6 remains a completed historical collection: 33 passes / 37 failures,
USD 0.73754105, with six confirmed reviews and its original provenance. The
[result index](results/d5/README.md) explains why the agreed formal comparison
will use five new collections, including GPT, and keeps the earlier USD 0.81427205
in the D5 spending ledger. No old result is erased, assigned a new execution
commit or selected into the new comparison based on its score.

## Release and remaining checks

The PR #32 lock correctly rejected these four changed files. The tested repair
was merged in PR #34; the new formal lock was then generated from that clean
merged commit and published in the separate lock-only PR #35. All five keyless
preflights passed at that release with 0 existing and 70 remaining trials each.
Members use its full merge SHA and verify its committed lock. No member generates
a replacement locally. The runtime hashes in this report match that release.

Only then proceed to each member's Codespaces status, unused r7 output path,
private key ownership, actual balance and read-only preflight. All five jobs
must complete the first-trial and five-trial checkpoints before any remaining 65.
The first five count toward each formal 70 if the frozen version stays unchanged.

This audit cannot establish real account access, real-time provider availability,
stable routing/aliases, adequate output on every case, or completion within each
budget. A provider/schema/usage problem pauses with retained evidence; normal
model failure does not trigger code tuning or a rerun. Future repairs require an
impact assessment before changing the experimental version or spending again.
D6, D7, final report/video and new-run human reviews remain separate unfinished
deliverables; this is readiness evidence, not a claim that the assignment is complete.

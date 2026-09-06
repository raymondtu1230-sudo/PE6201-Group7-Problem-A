# Provider compatibility repair and release conditions

## Current decision

This repair starts from merged main `97a85516c95deb16678aeb0d138e39523f7ec1db`
(PR #28). It addresses the Haiku parameter conflict using **one common requested
configuration for all five jobs**, not a special prompt or scoring adjustment.
**New paid jobs remain on hold.** This is a tested code repair, not a completed
release or a guarantee of provider availability or affordable completion.

The existing GPT r6 trial files, scores, human confirmations and original D5 lock
are preserved byte-for-byte. No real API key is used, and no model API is called
to develop or verify this change. No old trial is automatically rerun.

## Repair

- The shared generation block is now `temperature=0, max_tokens=4096`. The
  explicit `top_p=1` field is omitted for **all five jobs**. No per-member
  settings or silent fallback are introduced.
- Battery validation checks every configured model before an agent, output
  directory or provider request is created. The old two-sampling-field
  configuration is rejected, including when invoking live directly.
- The lower-level HTTP boundary also validates known parameter constraints.
  Haiku 4.5 rejects a simultaneous temperature/top_p request and temperature
  outside its [0, 1] range. Settings cannot override model, messages or routing.
- The independent synthetic provider now enforces Haiku's documented constraint
  throughout the existing full-battery and late-failure rehearsals. It does not
  call the new production validator, so a serializer regression can be detected.

Sources checked 6 September 2026: [Haiku migration guide](https://platform.claude.com/docs/en/models/haiku-4-5/migration-guide),
[Claude Messages API parameter ranges](https://platform.claude.com/docs/en/api/messages/create),
and [OpenRouter explicit/omitted parameter behavior](https://openrouter.ai/docs/api_reference/parameters).
These justify local rejection of the known incompatibility. They do not certify
every actual OpenRouter route or establish identical effective sampling across
different model families. In particular, omitting an explicit default must not
be represented as a proven byte-identical request or cost-equivalent change.

## Offline verification

The seven new tests in `tests/test_d5_provider_contracts.py` cover:

| Check | Required result |
| --- | --- |
| Direct Haiku request with both sampling fields | Reject before transport; zero requests |
| Invalid types, non-finite values, Haiku range, identity/routing overrides | Reject before transport |
| Incompatible common configuration | Reject for the entire battery |
| Preflight and direct live entry for each of five jobs | Old configuration rejected without creating output or constructing an agent |
| Actual serialized requests for all five models | Same requested fields and values; no top_p |
| Attempt to resume an archived r6 copy using the changed configuration | Reject before payment; copied evidence remains unchanged |
| A simulated USD 0.04 returned call at trial 6, 35 or 70 for every job | Retain cost and trial, return budget-stop code 4, request no later call/trial in the batch |

The spending test covers **15 combinations** of job and late-trial position.
Its charges are synthetic; it is not a claim that a provider billed that amount.
The existing suite additionally exercises staged 1 + 4 + 65 trials for every job,
unique keys, complete aggregation, 60 late model/provider failure scenarios,
HTTP 200 provider errors, HTTP failures, missing billing, interruption journals,
disk failures, concurrency and recovery. Ordinary scored model failures continue.

The complete suite ran with `scripts/check_d5_readiness.py`, which removes real
keys, denies socket/DNS operations and terminates after 300 seconds. Result:
**145 tests passed in 128.127 seconds; 0 network attempts and 0 paid model calls.**
The seven new tests also passed separately in 13.929 seconds. Compilation and
`git diff --check` pass. The original lock correctly rejects the changed runtime.
Git confirms no change to archived results, the lock, fixtures, answer key,
`src/claim_agent.py` or the scorer. Synthetic test locks describe temporary test
data; they are never published as the release lock.

## Budget is a separate completion constraint

The repair leaves the common **USD 0.035 per-trial stop threshold and USD 2.50
per-job threshold** unchanged. A returned charge can exceed a threshold while a
request is already in flight. The tests establish prompt stopping and retained
accounting, not a provider-enforced maximum bill or a guarantee of 70 responses.

For scale only, applying the [Haiku standard USD 1/5 per million token prices](https://openrouter.ai/anthropic/claude-haiku-4.5)
to GPT r6's measured input and non-reasoning output yields **USD 1.556622** over
70 trials. The largest re-priced trial is **USD 0.040475**, and five exceed
the current USD 0.035 threshold. This is a reference calculation, **not a Haiku
forecast**: its token lengths, reasoning and number of calls will differ.

Consequently the current limits may intentionally stop Haiku partway through a
job even after the parameter repair. Do not describe that as guaranteed full-run
readiness, raise limits silently, lower max_steps to improve apparent affordability,
or retry failures to improve scores. Resolve the common budget policy before
freezing the next formal release, then inspect actual cost after one smoke and
four more scheduled cases before a 65-trial continuation. A key-authentication
HTTP 200 establishes neither balance nor generation access.

## Frozen-version decision before release

The revised assignment's D5(b) says the comparison uses the same commit and v2
prompt, with MODEL as the changing variable (the declared fixed-model v1 job is
the explicit exception). This repair changes both runtime and requested settings.
It therefore **cannot simply relabel GPT r6 as a run of the repaired release**.
The unchanged lock and strict result identity checks deliberately prevent that.

Two distinct outcomes must not be confused:

1. GPT r6 remains complete historical evidence: 70 trials, final 33/70, cost
   USD 0.73754105, with the original code/settings manifest and confirmed reviews.
2. A formal table pooling that battery with newly repaired-version jobs is not
   established as compliant merely because prompts, fixtures and scores are unchanged.

The strict same-version route is a new common locked release and a new formal
battery under it, preserving r6 separately. This entails another paid GPT battery
and is **not authorized or started by this patch**. The alternative requires an
explicit instructor acceptance of disclosed compatibility-only version differences;
the assistant cannot invent that exception or assert that approval was given.

Before further payment, decide this comparison issue and the common budget policy.
Then merge the complete runtime/configuration repair, create the lock from that
clean merged baseline in a separate lock-only change, and verify it. Every member
uses the same selected release, a fresh designated output path and their own key.
Do not use archived r3/r5/r6 directories for a changed baseline.

The current `D5_LOCK.json` intentionally remains old, so verification of this
repair checkout must fail on the changed config/backend/runner until a legitimate
new release is made. Do not bypass verification, manually substitute old hashes,
or relax the result validator to hide version drift. No live command is supplied
by this repair note. Work ends after the reviewable patch and evidence are saved.

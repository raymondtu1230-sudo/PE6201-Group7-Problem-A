# D5 cross-model interface audit

**Historical PR #31 audit.** [D5_FINAL_RISK_CHECK.md](D5_FINAL_RISK_CHECK.md)
records the later full-suite rerun, additional reproduced faults and four runtime
repairs. Its evidence supersedes the runtime hashes in `cross_model_audit.json`.
The interface research below remains source evidence; PR #32's lock must be
replaced after those repairs. Use the current runbook and latest lock-only release.

Audit date: 6 September 2026. Starting main: `3c7a25dda028aafbbf4620e7ff09b03e391c0e35`.
The repair and evidence were merged in PR #31; the independent lock was published
in PR #32. This note records interface evidence. The current five-job collection
sequence is in [D5_MODEL_BATTERY.md](D5_MODEL_BATTERY.md).

## Collection scope

All five configured jobs have a full offline 70-trial rehearsal. The formal
comparison will use five new collections on one exact frozen checkout and the
published lock. Jobs 1–4 share v2; jobs 4 and 5 form the fixed-Gemini v2/v1 pair,
as required by Assignment D5(b), page 14. Every member runs the same 50-case,
70-trial schedule with their own key. No new-lock live collection has started.

GPT r6 keeps its original baseline, settings, trial files and confirmed reviews
as historical evidence, outside the new formal comparison. The
[result index](results/d5/README.md) explains the additional collection and accounts
for earlier spending. A release change does not change the identity of past calls.

## Five-job evidence matrix

"Offline checked" means the actual serializer/parser and local code were exercised
with injected responses. It does not mean a provider answered a paid request.

| Job / member | Model / prompt | Documented constraint and local evidence | Actual live status |
| --- | --- | --- | --- |
| 1 / TU WEIKANG | GPT-5 Mini / v2 | Native model/Chat Completions docs and gateway catalog checked. Catalog does not list temperature/top_p support. Full 70-trial offline rehearsal includes output exhaustion and refusal. | r6 complete on its original lock; no new-lock live run |
| 2 / CHEN KE | Qwen3 30B A3B Instruct 2507 / v2 | Catalog lists temperature and max_tokens. Model card identifies non-thinking mode. Shared textual dialogue checked offline. | Pending first trial |
| 3 / KANG XINGYAO | Claude Haiku 4.5 / v2 | Native contract forbids temperature plus top_p. Current request sends only temperature=0 and max_tokens=4096; invalid combination rejected before transport. | Pending first trial |
| 4 / YAO FANGXUAN | Gemini 2.5 Flash Lite / v2 | Catalog lists temperature and max_tokens. Text dialogue checked offline. No native function calls or thinking signatures are sent. | Pending first trial |
| 5 / HUANG YIHAN | Gemini 2.5 Flash Lite / v1 | Same model/configuration as job 4. Verified request difference is the declared v1 descriptor content, not member-specific instruction. | Pending first trial |

The request audit captures the real serialized body for all five configurations:
exactly model, messages, temperature and max_tokens; system/user/assistant/Observation
history is preserved. The four v2 message bodies have matching hashes for the same
input. The v1 hash differs as designed. Action calls are textual ReAct JSON parsed
locally, not native provider tool_calls. Native tool schema differences therefore do
not need model-specific adaptations in this implementation.

The configured endpoint is OpenRouter Chat Completions, not OpenAI's native endpoint.
OpenAI documents max_completion_tokens as including reasoning and visible output;
the gateway accepts the benchmark's max_tokens field and handles upstream translation.
We do not rename that gateway field or claim native OpenAI accepts this exact body.
The catalog does not advertise temperature/top_p for GPT-5 Mini, and default gateway
routing can ignore unsupported parameters. Therefore temperature=0 in the manifest is
a requested setting, not evidence of effective zero-temperature GPT sampling.

The public catalog's current top-provider output limits are 128,000 (GPT), 32,000
(Qwen), 64,000 (Haiku), and 65,535 (Gemini), all above 4,096. The catalog lists
Gemini one token below Google's native 65,536 ceiling. Route limits can differ.
Being below a maximum does not prove that 4,096 tokens is sufficient for every case;
reasoning, when used by a model, can consume its output allowance.

## Actual gap reproduced and repaired

Before this patch, an otherwise valid assistant message with null/blank content,
complete nonnegative billing and finish_reason=content_filter or length raised
PaidMalformedResponse and stopped the batch. This was reproduced using injected
documented response shapes, not a claimed real provider incident.

The patch identifies only explicit content_filter, length or refusal stops (including
native refusal and OpenAI-style message.refusal), with a valid assistant message
envelope and complete billing, as
model_output_failure. The case remains a scored failure, and the batch can continue.
No answer or decision is fabricated. Nonempty text is not rewritten. Unknown empty
responses, invalid envelopes, missing billing and explicit provider errors still stop.
An over-budget empty completion still stops and retains its charge.
Separate refusal text is preserved in both the request journal and retained trial;
it is not replaced with an invented answer. This OpenAI response shape is a documented
defensive fixture, not a claim that OpenRouter returned it in r6.

This changes only the treatment of these failed returns. It changes neither outbound
requests nor prompts, tools, fixtures, answer key, scoring rules, max_steps or budgets.
All r6 rows were checked: none entered the old paid_malformed_response branch, and all
stored code checks still reproduce. The patch therefore has no identified application
to the retained r6 observations. It does not prove that new stochastic calls would
reproduce r6's answers.

## Preserved result and comparison differences

r6 remains 70 trials, 33 passes / 37 failures, USD 0.73754105. All six confirmed
reviews remain intact. Its highest-cost trial was USD 0.02133245; zero trials hit
the old USD 0.035 cap, and total spend was below the old USD 2.50 job cap.

| Difference from r6 | Consequence |
| --- | --- |
| Explicit top_p=1 omitted in the later request | Requested configuration differs. OpenRouter leaves omitted values to providers and unsupported parameters can be ignored. Effective historical sampling is not proven identical. |
| Trial/job caps increased to USD 0.08 / 2.80 | r6 was not truncated by the former limits. Future models may have more spending headroom; disclose the thresholds. |
| Request validation and decimal budget arithmetic | Local compatibility/accounting changes, with no altered task content. |
| Explicit empty model stops now continue the battery | Such stops remain failures. This branch was not taken in r6. |

GPT's catalog support does not establish temperature=0 actually took effect in r6.
Qwen's recommended sampling settings differ from the shared benchmark settings;
recommendations are not acceptance requirements. We retain the selected benchmark
configuration rather than tune individual models after observing scores. Reasoning
defaults and provider routing are not fully controlled across families. Retain measured
reasoning/cached token details when returned; do not call every setting equivalent.

The strict existing aggregator accepts one lock. The formal table will contain
only the five designated `r7` directories after complete collection and review.
Old r3/r5/r6 are outside that denominator. The new GPT result will be used even if
its score is lower than r6; there is no selection of the better of two runs.
Historical r6 can be validated in its original release checkout with its original
lock. Its raw files and scores remain unchanged.

## Validation and limits

The final repaired runtime passed **31 selected tests in 110.680 seconds**:
network_attempts=0, paid_model_calls=0, r6_unchanged=true. This includes both full
five-job rehearsals and the late-failure matrices below. Runtime file hashes are
recorded with the results so the tested source can be compared with the release.

The bounded command is `python3 scripts/check_d5_cross_model.py --output results/d5-readiness/cross_model_audit.json`.
The machine-readable report records the selected tests, request hashes, recomputed
r6 checks and file hashes. This replaces no historical test results and does not
rerun the entire 147-test suite. Every job, including GPT, uses the actual 50-case,
70-trial schedule with 1 + 4 + 65 resumptions. There is a full multi-turn replay with
independent fake keys and final aggregation, plus another full battery containing
explicit empty model stops at trials 2, 6, 35 and 70. These replayed outputs are
software checks and do not predict model scores or real token consumption.

The late-failure matrix contains 60 model/provider scenarios across five jobs at
positions 6, 35 and 70, and 15 additional price-spike scenarios. It checks that ordinary
model failures continue, provider/billing problems stop, known charges survive, and
budget exhaustion does not cause a new call on resume. Additional selected checks
cover the exact job-budget boundary, HTTP errors, interruption checkpoints, disk
append failure, and a competing process. Tests use temporary directories and synthetic keys; an
audit hook blocks socket/DNS operations. Public documentation/catalog GETs are
separate read-only research and are not counted as model-generation calls.

Still unverified: each pending member's key ownership, account credit, generation
access and rate limits; actual provider behavior, latency, routing, token lengths and
scores for that member; and the state of the user's Codespaces. The initial five
scheduled trials cover ordinary cases, not every negative or late-history shape.
They are an integration checkpoint, not proof that later trials cannot fail.

## Sources inspected

- [OpenRouter model catalog](https://openrouter.ai/api/v1/models): selected facts in `results/d5-readiness/model_contracts.json`.
- [OpenAI GPT-5 Mini](https://developers.openai.com/api/docs/models/gpt-5-mini): target model, context/output ceilings and reasoning support.
- [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create): native completion-token accounting and nullable content / separate refusal field; gateway translation is a separate layer.
- [OpenRouter parameters](https://openrouter.ai/docs/api_reference/parameters): omitted versus explicit parameters.
- [Provider routing](https://openrouter.ai/docs/guides/routing/provider-selection): unsupported parameters/default routing; max_tokens routing constraint.
- [Chat completion reference](https://openrouter.ai/docs/api_reference/overview): nullable content, normalized/native finish reasons and usage.
- [Usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting): returned token counts and cost; no extra usage parameter is needed.
- [Errors and debugging](https://openrouter.ai/docs/api_reference/errors-and-debugging): HTTP and response-body errors.
- [Haiku 4.5 migration guide](https://platform.claude.com/docs/en/models/haiku-4-5/migration-guide): exclusive sampling parameters and refusal handling.
- [Qwen's model card](https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507): non-thinking mode and recommended settings.
- [Gemini 2.5 Flash Lite](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite) and [thinking](https://ai.google.dev/gemini-api/docs/thinking): native limits and optional/default thinking.
- [OpenRouter reasoning](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens): reasoning configuration and billing.

The executable operating sequence is in [D5_MODEL_BATTERY.md](D5_MODEL_BATTERY.md).

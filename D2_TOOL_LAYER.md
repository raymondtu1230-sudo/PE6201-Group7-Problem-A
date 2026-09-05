# D2 — Tool-layer design and scripted measurements

This deliverable retains one hand-written ReAct agent. Measurements below are deterministic offline measurements, **not live-model claims**.

## D2(a): shortest defensible set

Before considering a new tool we applied this order: (1) widen a retained tool's parameters, (2) return more relevant evidence in one call, (3) move deterministic validation/bounding/deduplication outside the model loop, and only then (4) add a tool. No seventh tool was justified.

| Tool | Concrete task that fails without it | Possible confusion / differentiation | Cost even if never called | Verdict / alternative considered |
|---|---|---|---|---|
| `get_claim` | Claim facts and duplicate comparison cannot be established. | Unlike policy lookup, it owns claim/history evidence only. | Descriptor tokens and interface/test surface. | Retain; merged claim and duplicate-history reads avoids an extra tool. |
| `lookup_policy` | Eligibility, dates and remaining limit cannot be established. | Coverage is line/rule-specific; this is member/policy-level. | Same fixed prompt/schema cost. | Retain; returning member plus policy avoids `get_member`. |
| `check_coverage` | Exclusions, documents and preauthorisation requirement cannot be resolved. | Preauthorisation checks a required authorisation instance, not whether one is required. | Largest repeated-call opportunity and descriptor cost. | Retain; deterministic document checking remains in this call. Removed ambiguous `member_id` alternative rather than widen it. |
| `get_preauthorisation` | Required authorisation validity on service date cannot be proved. | Called only after coverage says it is required. | Descriptor/test surface although many lines do not need it. | Retain; merging into coverage would waste history reads and remove the coverage decision point. |
| `get_hospital_status` | Final panel status cannot be reported. | Provider-level only; claim merely supplies its ID. | Descriptor and sometimes avoidable early parallel read. | Retain because the required final evidence is in a separate source; defer in sequential mode. |
| `issue_decision_letter` | The explicit confirmation gate and auditable simulated issuance cannot be exercised. | Only write tool; all others are reads. | Significant safety/schema prompt cost even when blocked. | Retain as a simulation; moving the append outside the loop was considered but would hide the required gated action. |

Considered removals/merges were therefore `get_member` into policy (already merged), duplicate lookup into claim (already merged), preauthorisation into coverage (rejected), and write outside the loop (rejected). This is the shortest set that preserves each distinct source, decision point, and explicit gate.

## D2(b): six-field descriptors

The executable descriptor block is `TOOL_DESCRIPTORS` in `src/claim_agent.py`; it is included in every modeled input. Each row below maps its six mandatory fields.

| NAME + SIGNATURE | WHAT | INPUT (type and bad-value behaviour) | RETURNS (explicit bound) | FAILS WHEN | IRREVERSIBLE? |
|---|---|---|---|---|---|
| `get_claim(claim_id: str)` | Claim and duplicate evidence | non-empty `CLM-*`; returns `invalid_input` | structured claim/comparisons, ≤8,000 JSON chars | invalid or absent ID | No |
| `lookup_policy(member_id: str)` | Member/policy eligibility | `M-*`; returns `invalid_input` | member/policy, ≤8,000 | invalid/absent record | No |
| `check_coverage(code: str, documents: list[str], policy_id: str)` | Line rules | strings, list of strings, `POL-*`; returns `invalid_input` | one line result, ≤8,000 | bad/unknown policy or procedure | No |
| `get_preauthorisation(member_id: str, code: str, date: str)` | Date-valid authorisation | `M-*`, code, strict ISO date; returns `invalid_input` | selected record and ≤10 matches, ≤8,000 | bad values; absence is `found=false` | No |
| `get_hospital_status(hospital_id: str)` | Panel evidence | `H-*`; returns `invalid_input` | hospital result, ≤8,000 | invalid/absent record | No |
| `issue_decision_letter(claim_id: str, decision_record: object, decision_complete: bool)` | Simulated local append | structured final decision plus literal `true`; bad values are blocked | gate result, ≤8,000 | incomplete, unconfirmed, or already written | **Yes** — completion + autonomy + confirmation + zero-write gate |

**Poka-yoke changes.** (1) `check_coverage` has one unambiguous policy key; removing the old member-or-policy alternative makes accidental precedence/wrong-policy resolution impossible. (2) strict ISO date validation prevents lexicographic authorisation decisions on malformed dates. (3) the literal `decision_complete=true` gate makes a premature/empty simulated write impossible.

Both `get_claim` shapes remain selectable with `descriptor_version=v1|v2` without duplicating the agent. Profiling all 50 claims selected it as the rewrite target: v1 totals 20,215 characters (mean 404.30, max 679); v2 totals 19,015 (mean 380.30, max 559). V2 retains the authoritative claim plus explicit matched/differing field arrays and exact-match flag, removes repeated derived date/count fields, adds `shape_version`, and remains bounded/auditable. See `results/d2/observation_profile.json`.

## D2(c): execution strategy and dependencies

`execution_mode` is validated as `sequential` or `parallel`. Sequential emits each independent call in a separate Action/model turn. Parallel may share an Action block **only when neither call requires the other's output**.

| Before | After | Reason |
|---|---|---|
| — | `get_claim` | IDs, lines, service date and duplicate evidence originate here. |
| `get_claim` | `lookup_policy`, later hospital/line work | Member and hospital/line identifiers must be authoritative. |
| `lookup_policy` | `check_coverage` | Policy identity/status precedes line rules. |
| all coverage results | required `get_preauthorisation` calls | Coverage determines which checks are required. |
| complete decision | `issue_decision_letter` | Gated simulated write is last and at most once. |

Parallel mode batches coverage lines and the independent hospital read after claim/policy, then batches independent required authorisations. It can waste a hospital call when later coverage requests a document or detects hostile content, and it removes the useful per-line stop/reconsider point. Sequential preserves those model decision points at additional turns/tokens.

Over 70 trials (40 ordinary once, 10 negative three times), the committed scripted results report approximate token estimates including system/base text, the complete descriptor block, and accumulated history on every turn. Provider pricing is zero for the local planner, so estimated cost is `$0.00`. The live same-cheap-model v1/v2 comparison remains pending for D5. The sequential/parallel comparison is the scripted measurement required by D2(c); it does not require an additional paid battery. D5 provider-measured usage supplies the live cost evidence, while the scripted estimates remain explicitly labelled as estimates.

## Pre-D5 descriptor evidence

`results/d2/observation_profile.json` reports both serialized character size and the
explicit deterministic approximation `ceil(UTF-8 compact-JSON bytes / 4)` for every
v1/v2 `get_claim` result. This is an approximate byte-ratio method, not a provider
tokenizer. `versioned_full_scorer.json` runs both versions through the unchanged D4
`score_trial` contract over all 70 trials, and `descriptor_guardrails.json` compares the
15 scripted guardrail cases for both versions. Exact provider token totals and a
same-model live v1/v2 pass-rate comparison remain pending until controlled D5.

# D0 Pre-build Design Record

**Course:** PE6201 A2 Applied AI System

**Chosen problem:** Problem A — health-insurance claim first response

**Planned architecture:** one hand-written, single-agent ReAct control loop

**Planned autonomy setting:** confirm

## D0(a): Position on the seven-rung ladder

This problem belongs on **rung 7 — Agent**. The lower rungs can contribute, but none provides the complete required system:

- **Rung 1 — Single call:** one call could classify or draft a response, but it cannot iteratively retrieve and verify the relevant records.
- **Rung 2 — Prompt chain:** a chain could split the reasoning into stages, but it imposes the same predetermined sequence on every claim.
- **Rung 3 — Routing:** routing could select a predefined lane, but it would not conduct variable evidence gathering within a claim.
- **Rung 4 — Parallelisation:** parallel calls could run predetermined independent checks, but they would not decide the sequence at runtime.
- **Rung 5 — Orchestrator–workers:** workers could divide checks, but multi-agent coordination adds unnecessary cost and failure surface and is outside the required single-agent architecture.
- **Rung 6 — Evaluator–optimiser:** an evaluator could critique a proposed decision, but it would not replace adaptive evidence gathering and could add an uncertain number of rounds.

Rung 7 lets one ReAct agent choose the next tool from its observations, stop early, repeat line-level checks when needed, and place the simulated write behind a gate. This fits Problem A because claims vary in line-item count and some procedures require pre-authorisation. A lapsed policy should stop early, while a partly payable claim needs line-by-line treatment. Rung 7 also has costs: paths, turn count and per-case cost are not fully predictable, so the system needs caps, instrumentation and outcome-based evaluation.

### Workflow tests

- **Who decides the sequence?** The agent should choose the next check from the evidence returned so far, within fixed safety rules.
- **Do the steps vary?** Yes. Their number and order vary with policy status, line count, procedure requirements, pre-authorisation evidence and missing information.
- **Can every path be enumerated?** No. The model selects its next tool at runtime and may re-query, so the system must be tested by outcomes rather than by testing every possible path.
- **Is cost predictable?** Not exactly per claim, because the required checks and turns vary. It must instead be bounded and measured.

An agent is warranted only if both necessary conditions hold: **the steps are not known in advance**, and **ground truth is returned after each step**. Problem A is intended to meet both conditions through adaptive record checks against systems of record.

**Retrieval** uses a query selected in advance by code; it cannot loop or re-query and is read-only. **Agentic retrieval** lets the model select retrieval at runtime and re-query, but remains read-only. **An agent** controls the loop and can perform a state-changing action.

Problem A's first simulated state-changing action is `issue_decision_letter`. It will be gated by operator confirmation and simulated only by appending one structured decision record.

## D0(b): When not to build an agent

### Ground-truth test

The model is not the authority. The local claim, member, policy, hospital, procedure, preauthorisation and decision-log lookups are systems of record that return within the same run at machine speed, normally within milliseconds or seconds. Their results can contradict the model, and the decision log immediately identifies whether a claim has already received a decision. The workflow must follow this evidence rather than preserve a model assumption. If these sources cannot provide timely, checkable ground truth, an agent should not be built for this task.

### Reliability-arithmetic test

The reliability diagnostic is:

\[
s = P^{(1/T)}
\]

Here, `P` is the **measured end-to-end run pass rate from D4**, `T` is the **instrumented median number of turns in one run**, and `s` is the **implied average per-step reliability**. It is only a diagnostic, not a required reliability.

- **Measured `P`:** `[PLACEHOLDER — final v2 pass rate from D4]`
- **Median `T`:** `[PLACEHOLDER — instrumented median turns across the evaluation runs]`
- **Implied `s`:** `[PLACEHOLDER — calculate as P^(1/T)]`

If the results show unacceptable compounding unreliability, the planned responses are to:

- improve weak steps through clearer descriptors and bounded return shapes;
- reduce unnecessary turns through dependency-aware parallel calls or ordinary code; and
- make failures recoverable through safe stopping, specific requests and escalation before the gated write.

This arithmetic is only a planning approximation. It assumes that step outcomes are independent and that every step has equal reliability; real workflow errors may be correlated and steps may have very different risks.

## D0(c): What good looks like

1. For every evaluated response, the decision is traceable to the system-of-record evidence used for it.
2. For every evaluated claim, every claim line matches its labelled disposition; a partly payable claim remains `approve_in_principle` when every line resolves, while excluded lines and approved/refused totals are recorded separately.
3. In every run, `issue_decision_letter` occurs at most once and only after the required evidence has been checked and the operator has confirmed the action.
4. In every test with missing or unsupported information, the fixed routing rule is followed: name the specific missing item when an ask is required, or name the single trigger and recipient when escalation is required, rather than inventing information.
5. Across evaluation runs, each run remains within evidence-based turn and budget caps, and its measured handling cost is lower than the measured manual-handling baseline.

## Pre-build status

This document was written before agent implementation. It will later be updated only with measured evaluation values and confirmed scaffold details.

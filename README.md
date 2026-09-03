# PE6201 Assignment 2 — Group 7, Problem A

This repository currently implements **D1 only**: an offline, single-agent ReAct
foundation for a health-insurance claim first response. The hand-written loop in
`src/claim_agent.py` owns `Thought → Action → Observation → repeat → Final`; no
agent framework or sub-agent is used. Fixture and tool evidence is authoritative.

The default `scripted` backend is deterministic and makes no network or paid model
calls. `issue_decision_letter` is only a simulation: with explicit confirmation it
appends one structured record to local `decision_records.jsonl`; otherwise the gate
blocks the write. Do not use this demonstration with real insurance data.

## Exact reproduction

From the repository root, using Python 3.10 or newer:

```bash
python3 make_fixtures_A.py
python3 check_my_data.py
python3 -m py_compile src/claim_agent.py
python3 -m unittest discover -s tests -v
```

Run a case without confirmation (the simulated write is blocked):

```bash
python3 -m src.claim_agent CLM-8842
```

Run with confirmation (one local JSONL record may be appended):

```bash
python3 -m src.claim_agent CLM-8842 --confirm
```

Execute the demonstration notebook from a clean kernel when Jupyter is installed:

```bash
jupyter nbconvert --to notebook --execute D1_AGENT_BUILD.ipynb \
  --output /tmp/D1_AGENT_BUILD.executed.ipynb
```

## Scope

The committed `data_A/*.json` files are generated unchanged from the teacher's
`make_fixtures_A.py`, and the 15 labels in `expected_outcomes_A.json` are the D1
truth set. This build does not claim D2–D7, add the later evaluation cases, provide
a UI or deployment, send letters, or contain credentials.

"""Offline, vendor-neutral D1 single-agent ReAct claim workflow.

The control loop is deliberately owned here: ``call_model`` produces a Thought
and an Action, the loop executes the JSON tool calls, appends Observations, and
repeats until Final.  The default backend is deterministic and uses only local
fixture records; it routes from observations rather than claim identifiers.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

# Vendor-neutral configuration (a live adapter may be added inside call_model).
BACKEND = "scripted"
MODEL = "local-rule-planner"
BASE_URL = ""
INPUT_TOKEN_PRICE_PER_MILLION = 0.0
OUTPUT_TOKEN_PRICE_PER_MILLION = 0.0
DEFAULT_MAX_MODEL_CALLS = 12
DEFAULT_BUDGET_USD = 0.01
MAX_TOOL_RESULT_CHARS = 8_000

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data_A"
DEFAULT_LOG = ROOT / "decision_records.jsonl"


@dataclass
class RunResult:
    case_id: str
    decision_record: Optional[dict[str, Any]]
    trace: list[dict[str, Any]]
    action_turns: int
    model_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    halt_reason: str
    write_count: int


@dataclass
class _State:
    case_id: str
    autonomy: str
    confirmed: bool
    trace: list[dict[str, Any]] = field(default_factory=list)
    observations: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    action_keys: set[str] = field(default_factory=set)
    action_turns: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    halt_reason: str = ""
    decision: Optional[dict[str, Any]] = None
    write_count: int = 0


class ClaimAgent:
    """One hand-written ReAct agent with a confirmation-gated local write."""

    def __init__(self, data_dir: Path | str = DATA_DIR, log_path: Path | str = DEFAULT_LOG,
                 backend: str = BACKEND, model: str = MODEL,
                 max_model_calls: int = DEFAULT_MAX_MODEL_CALLS,
                 budget_usd: float = DEFAULT_BUDGET_USD) -> None:
        self.data_dir, self.log_path = Path(data_dir), Path(log_path)
        self.backend, self.model = backend, model
        self.max_model_calls, self.budget_usd = max_model_calls, budget_usd
        self.tables = {name: self._load(name) for name in (
            "claims", "members", "policies", "procedures", "preauthorisations",
            "hospitals", "required_documents", "decided_claims")}

    def _load(self, name: str) -> list[dict[str, Any]]:
        with (self.data_dir / f"{name}.json").open(encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _find(rows: list[dict[str, Any]], key: str, value: Any) -> Optional[dict[str, Any]]:
        return next((dict(row) for row in rows if row.get(key) == value), None)

    # ---- tools -----------------------------------------------------------
    def get_claim(self, claim_id: str) -> dict[str, Any]:
        claim = self._find(self.tables["claims"], "claim_id", claim_id)
        if not claim:
            return {"found": False, "claim_id": claim_id}
        comparison_fields = ("member_id", "hospital_id", "date_of_service", "lines")
        comparisons = []
        for prior in self.tables["decided_claims"]:
            matched = [field for field in comparison_fields if prior.get(field) == claim.get(field)]
            differing = [field for field in comparison_fields if field not in matched]
            # Retain exact matches and useful one-field near misses. This makes a
            # non-duplicate conclusion auditable without flooding the result with
            # unrelated claim history.
            if len(matched) >= 3:
                comparisons.append({
                    "prior_claim_id": prior["claim_id"],
                    "exact_match": not differing,
                    "matched_fields": matched,
                    "differing_fields": differing,
                    "current_line_count": len(claim["lines"]),
                    "prior_line_count": len(prior["lines"]),
                    "current_date_of_service": claim["date_of_service"],
                    "prior_date_of_service": prior["date_of_service"],
                })
        duplicate = next((item for item in comparisons if item["exact_match"]), None)
        return {"found": True, "claim": claim,
                "prior_matching_claim": duplicate and duplicate["prior_claim_id"],
                "duplicate_comparisons": comparisons}

    def lookup_policy(self, member_id: str) -> dict[str, Any]:
        member = self._find(self.tables["members"], "member_id", member_id)
        if not member:
            return {"found": False, "member_id": member_id}
        policy = self._find(self.tables["policies"], "policy_id", member["policy_id"])
        return {"found": policy is not None, "member": member, "policy": policy}

    def check_coverage(self, procedure_code: str, attached_documents: list[str],
                       policy_id: Optional[str] = None,
                       member_id: Optional[str] = None) -> dict[str, Any]:
        if not policy_id and member_id:
            lookup = self.lookup_policy(member_id)
            policy_id = (lookup.get("policy") or {}).get("policy_id")
        policy = self._find(self.tables["policies"], "policy_id", policy_id)
        procedure = self._find(self.tables["procedures"], "code", procedure_code)
        required = self._find(self.tables["required_documents"], "procedure_code", procedure_code)
        if not policy or not procedure:
            return {"resolved": False, "procedure_code": procedure_code,
                    "error": "policy_or_procedure_not_found"}
        exclusion = next((x for x in policy["exclusions"] if x["code"] == procedure_code), None)
        missing_doc = required["document"] if required and required["document"] not in attached_documents else None
        return {"resolved": True, "procedure_code": procedure_code,
                "covered": exclusion is None, "exclusion_rule": exclusion and exclusion["rule"],
                "requires_preauth": procedure["requires_preauth"],
                "required_document": required and required["document"],
                "missing_document": missing_doc, "description": procedure["description"]}

    def get_preauthorisation(self, member_id: str, procedure_code: str,
                             date_of_service: str) -> dict[str, Any]:
        matches = [dict(x) for x in self.tables["preauthorisations"]
                   if x["member_id"] == member_id and x["procedure_code"] == procedure_code]
        valid = next((x for x in matches if x["valid_from"] <= date_of_service <= x["valid_to"]), None)
        return {"procedure_code": procedure_code, "date_of_service": date_of_service,
                "found": bool(matches), "valid": valid is not None,
                "authorisation": valid, "matches": matches}

    def get_hospital_status(self, hospital_id: str) -> dict[str, Any]:
        hospital = self._find(self.tables["hospitals"], "hospital_id", hospital_id)
        return {"found": hospital is not None, "hospital": hospital}

    def issue_decision_letter(self, claim_id: str, decision_record: dict[str, Any],
                              *, state: _State) -> dict[str, Any]:
        """Simulate issuance by one local JSONL append, and only after confirmation."""
        if state.write_count:
            return {"written": False, "gate_result": "blocked_already_written"}
        if state.autonomy != "confirm" or not state.confirmed:
            return {"written": False, "gate_result": "blocked_confirmation_required"}
        record = dict(decision_record)
        record.update({"timestamp": datetime.now(timezone.utc).isoformat(),
                       "case_id": claim_id, "autonomy_setting": state.autonomy,
                       "gate_result": "confirmed", "turns": state.action_turns,
                       "estimated_cost": state.estimated_cost})
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        state.write_count += 1
        state.decision = record
        return {"written": True, "gate_result": "confirmed"}

    # ---- explicit ReAct mechanics ---------------------------------------
    def _tool_map(self) -> dict[str, Callable[..., dict[str, Any]]]:
        return {name: getattr(self, name) for name in (
            "get_claim", "lookup_policy", "check_coverage", "get_preauthorisation",
            "get_hospital_status", "issue_decision_letter")}

    def execute_action_block(self, action_text: str, state: _State) -> bool:
        """Parse one JSON object or list and execute every valid, novel call."""
        try:
            calls = json.loads(action_text)
        except (json.JSONDecodeError, TypeError):
            state.halt_reason = "malformed_action"
            state.trace.append({"Observation": {"error": "malformed_action"}})
            return False
        calls = calls if isinstance(calls, list) else [calls]
        if not calls or not all(isinstance(x, dict) for x in calls):
            state.halt_reason = "malformed_action"
            return False
        pending = []
        for call in calls:
            name, args = call.get("tool"), call.get("arguments", {})
            if name not in self._tool_map():
                state.halt_reason = "unknown_tool"
                state.trace.append({"Observation": {"error": "unknown_tool", "tool": name}})
                return False
            if not isinstance(args, dict):
                state.halt_reason = "malformed_action"
                return False
            key = json.dumps(call, sort_keys=True)
            if key in state.action_keys:
                state.trace.append({"Observation": {"tool": name, "deduplicated": True}})
                continue
            state.action_keys.add(key)
            pending.append((name, args))

        def invoke(item: tuple[str, dict[str, Any]]) -> dict[str, Any]:
            name, args = item
            return (self.issue_decision_letter(**args, state=state) if name == "issue_decision_letter"
                    else self._tool_map()[name](**args))

        # Independent reads in the same Action block run together. State-changing
        # issuance is intentionally never mixed into a concurrent batch.
        try:
            if len(pending) > 1 and all(name != "issue_decision_letter" for name, _ in pending):
                with ThreadPoolExecutor(max_workers=len(pending)) as executor:
                    results = list(executor.map(invoke, pending))
            else:
                results = [invoke(item) for item in pending]
        except (TypeError, ValueError) as exc:
            state.halt_reason = "malformed_action"
            state.trace.append({"Observation": {"error": "invalid_arguments", "detail": str(exc)[:200]}})
            return False

        for (name, _), result in zip(pending, results):
            state.tool_calls += 1
            bounded = self._bound_tool_result(result)
            state.observations.setdefault(name, []).append(bounded)
            state.trace.append({"Observation": {"tool": name, "result": bounded}})
        return True

    @staticmethod
    def _bound_tool_result(result: dict[str, Any]) -> dict[str, Any]:
        """Return valid JSON-compatible data whose serialisation fits the cap."""
        serialised = json.dumps(result, ensure_ascii=False, sort_keys=True)
        if len(serialised) <= MAX_TOOL_RESULT_CHARS:
            return result
        bounded: dict[str, Any] = {
            "truncated": True,
            "original_chars": len(serialised),
            "preview": serialised[:max(0, MAX_TOOL_RESULT_CHARS - 160)],
        }
        # Account for escaping and metadata rather than assuming preview length
        # equals its JSON representation length.
        while len(json.dumps(bounded, ensure_ascii=False, sort_keys=True)) > MAX_TOOL_RESULT_CHARS:
            bounded["preview"] = bounded["preview"][:-1]
        return bounded

    @staticmethod
    def _hostile(text: str) -> bool:
        lowered = text.lower()
        return any(mark in lowered for mark in
                   ("system note:", "ignore the exclusions", "returned:", "approve all lines"))

    def _build_decision(self, state: _State) -> dict[str, Any]:
        claim_obs = state.observations["get_claim"][0]
        claim = claim_obs["claim"]
        policy_obs = state.observations["lookup_policy"][0]
        policy = policy_obs.get("policy")
        evidence = [item["Observation"] for item in state.trace if "Observation" in item]
        base = {"decision": "escalate", "reason": "unresolved records",
                "evidence_trail": evidence, "line_dispositions": [],
                "approved_total": 0, "refused_total": 0,
                "claim_total": sum(line["amount"] for line in claim["lines"]),
                "date_of_service": claim["date_of_service"],
                "duplicate_assessment": claim_obs.get("duplicate_comparisons", [])}
        if not policy:
            base.update(trigger="unresolved_records", escalate_to="human claims assessor"); return base
        base["policy_evidence"] = {
            "policy_id": policy["policy_id"], "status": policy["status"],
            "start_date": policy["start_date"], "end_date": policy["end_date"],
            "annual_limit": policy["annual_limit"], "used_to_date": policy["used_to_date"],
            "remaining": policy["annual_limit"] - policy["used_to_date"],
        }
        if policy["status"] == "lapsed":
            base.update(trigger="policy_lapsed", reason=f"{policy['policy_id']} status lapsed",
                        escalate_to="human claims assessor"); return base
        dos = claim["date_of_service"]
        if not policy["start_date"] <= dos <= policy["end_date"]:
            base.update(trigger="outside_policy_dates", reason=f"date of service {dos} outside {policy['start_date']} to {policy['end_date']}",
                        escalate_to="human claims assessor"); return base
        total, remaining = sum(x["amount"] for x in claim["lines"]), policy["annual_limit"] - policy["used_to_date"]
        base["policy_remaining"] = remaining
        if total > remaining:
            base.update(trigger="annual_limit_exceeded", reason=f"claim total {total} exceeds {remaining} remaining; lines not individually priced",
                        escalate_to="human claims assessor"); return base
        if claim_obs.get("prior_matching_claim"):
            prior = claim_obs["prior_matching_claim"]
            base.update(trigger="duplicate_claim", reason=f"matches prior {prior} on member, hospital, date of service, and lines",
                        escalate_to="human claims assessor"); return base
        coverages = {x["procedure_code"]: x for x in state.observations.get("check_coverage", [])}
        for line in claim["lines"]:
            cov = coverages.get(line["code"])
            if not cov or not cov.get("resolved"):
                base.update(trigger="unresolved_records", reason=f"coverage unresolved for line {line['code']}",
                            escalate_to="human claims assessor"); return base
            disposition = {"procedure_code": line["code"], "amount": line["amount"]}
            if not cov["covered"]:
                disposition.update(disposition="refused", rule=cov["exclusion_rule"])
                base["refused_total"] += line["amount"]
            else:
                disposition["disposition"] = "covered"
                base["approved_total"] += line["amount"]
            base["line_dispositions"].append(disposition)
        if self._hostile(claim.get("narrative", "")):
            base.update(trigger="instruction_in_member_narrative",
                        reason="member-supplied instruction/tool imitation found and not followed; real coverage evidence used",
                        escalate_to="human claims assessor")
            return base
        for line in claim["lines"]:
            cov = coverages[line["code"]]
            if cov.get("missing_document"):
                missing = cov["missing_document"].replace("_", " ")
                return {**base, "decision": "request_document", "trigger": None,
                        "missing": f"{missing} for line {line['code']}",
                        "reason": f"required {missing} absent for line {line['code']}"}
            if cov["covered"] and cov.get("requires_preauth"):
                auth = next((x for x in state.observations.get("get_preauthorisation", [])
                             if x["procedure_code"] == line["code"]), None)
                disposition = next(x for x in base["line_dispositions"]
                                   if x["procedure_code"] == line["code"])
                disposition["preauthorisation_evidence"] = auth or {"found": False, "valid": False}
                if not auth or not auth["valid"]:
                    prefix = "current pre-authorisation" if auth and auth["found"] else "pre-authorisation reference"
                    return {**base, "decision": "request_document", "trigger": None,
                            "missing": f"{prefix} for line {line['code']}, valid on {dos}",
                            "reason": f"pre-authorisation absent or not valid for line {line['code']} on {dos}"}
                disposition["preauthorisation"] = auth["authorisation"]
        hospital = state.observations.get("get_hospital_status", [{}])[0].get("hospital")
        if not hospital:
            base.update(trigger="unresolved_records", reason="hospital record unresolved",
                        escalate_to="human claims assessor"); return base
        base.update(decision="approve_in_principle", trigger=None,
                    reason="all lines resolved; excluded lines remain line-level refusals",
                    hospital_status={"hospital_id": hospital["hospital_id"], "panel": hospital["panel"]})
        return base

    def call_model(self, state: _State) -> str:
        """Return scripted Thought/Action or Final; no network or paid call occurs."""
        if self.backend != "scripted":
            raise RuntimeError("No live backend configured; provide an isolated adapter explicitly")
        obs = state.observations
        if "get_claim" not in obs:
            return f'Thought: Retrieve the authoritative claim.\nAction: {json.dumps({"tool":"get_claim","arguments":{"claim_id":state.case_id}})}'
        claim_obs = obs["get_claim"][0]
        if not claim_obs.get("found"):
            state.decision = {"decision": "escalate", "trigger": "unresolved_records",
                              "reason": "claim not found", "evidence_trail": [],
                              "escalate_to": "human claims assessor"}
            return "Final: claim record unresolved; escalate safely"
        claim = claim_obs["claim"]
        if "lookup_policy" not in obs:
            return f'Thought: Resolve policy before dependent checks.\nAction: {json.dumps({"tool":"lookup_policy","arguments":{"member_id":claim["member_id"]}})}'
        policy = obs["lookup_policy"][0].get("policy")
        if (not policy or policy["status"] == "lapsed" or
                not policy["start_date"] <= claim["date_of_service"] <= policy["end_date"] or
                sum(x["amount"] for x in claim["lines"]) > policy["annual_limit"] - policy["used_to_date"] or
                claim_obs.get("prior_matching_claim")):
            state.decision = self._build_decision(state)
        elif "check_coverage" not in obs:
            calls = [{"tool": "check_coverage", "arguments": {"policy_id": policy["policy_id"],
                      "procedure_code": line["code"], "attached_documents": claim["documents"]}}
                     for line in claim["lines"]]
            calls.append({"tool": "get_hospital_status", "arguments": {"hospital_id": claim["hospital_id"]}})
            return f'Thought: Coverage calls are independent by line; run them with hospital lookup.\nAction: {json.dumps(calls)}'
        else:
            needed = [x for x in obs["check_coverage"] if x.get("covered") and x.get("requires_preauth")]
            have = {x["procedure_code"] for x in obs.get("get_preauthorisation", [])}
            todo = [x for x in needed if x["procedure_code"] not in have]
            if todo:
                calls = [{"tool": "get_preauthorisation", "arguments": {"member_id": claim["member_id"],
                          "procedure_code": x["procedure_code"], "date_of_service": claim["date_of_service"]}}
                         for x in todo]
                return f'Thought: Fetch only required pre-authorisations after coverage observations.\nAction: {json.dumps(calls)}'
            state.decision = self._build_decision(state)
        if "issue_decision_letter" not in obs:
            action = {"tool": "issue_decision_letter", "arguments": {"claim_id": state.case_id,
                      "decision_record": state.decision}}
            return f'Thought: Decision is evidence-based; request the confirmation-gated simulated write.\nAction: {json.dumps(action)}'
        return f"Final: {state.decision['decision']} — {state.decision['reason']}"

    def run(self, claim_id: str, *, confirm: bool = False, autonomy: str = "confirm") -> RunResult:
        state = _State(case_id=claim_id, autonomy=autonomy, confirmed=confirm)
        while state.model_calls < self.max_model_calls:
            if state.estimated_cost > self.budget_usd:
                state.halt_reason = "budget_cap"; break
            response = self.call_model(state)
            state.model_calls += 1
            state.input_tokens += max(1, len(json.dumps(state.trace)) // 4)
            state.output_tokens += max(1, len(response) // 4)
            state.estimated_cost = ((state.input_tokens * INPUT_TOKEN_PRICE_PER_MILLION +
                                     state.output_tokens * OUTPUT_TOKEN_PRICE_PER_MILLION) / 1_000_000)
            thought = re.search(r"Thought:\s*(.*)", response)
            if thought:
                state.trace.append({"Thought": thought.group(1)})
            if response.startswith("Final:"):
                state.trace.append({"Final": response[6:].strip()})
                state.halt_reason = "final"
                break
            action = response.split("Action:", 1)
            if len(action) != 2:
                state.halt_reason = "malformed_action"; break
            state.action_turns += 1
            state.trace.append({"Action": action[1].strip()})
            if not self.execute_action_block(action[1].strip(), state):
                break
        else:
            state.halt_reason = "model_call_cap"
        return RunResult(claim_id, state.decision, state.trace, state.action_turns,
                         state.model_calls, state.tool_calls, state.input_tokens,
                         state.output_tokens, state.estimated_cost, state.halt_reason,
                         state.write_count)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the offline D1 claim agent")
    parser.add_argument("claim_id")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ClaimAgent().run(args.claim_id, confirm=args.confirm).__dict__, indent=2))

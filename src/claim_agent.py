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
AUTONOMY_MODES = ("suggest", "confirm", "act")
MAX_TOOL_RESULT_CHARS = 8_000
TOOL_RESULT_SIZE_BOUND = 8_000
EXECUTION_MODES = ("sequential", "parallel")
DESCRIPTOR_VERSIONS = ("v1", "v2")

# These dictionaries are also the exact descriptor block placed in every model
# input. Keeping documentation and accounting sourced from one object prevents
# descriptor drift.
TOOL_DESCRIPTORS = {
    "get_claim": {"signature": "get_claim(claim_id: str)", "what": "Fetch a claim and bounded duplicate evidence.", "input": "Non-empty CLM-* string; bad values return invalid_input.", "returns": "Object containing found, claim, and duplicate evidence; <=8000 JSON characters.", "fails_when": "The identifier is invalid or no fixture row exists.", "irreversible": "No."},
    "lookup_policy": {"signature": "lookup_policy(member_id: str)", "what": "Resolve the member and its policy.", "input": "Non-empty M-* string; bad values return invalid_input.", "returns": "Found flag, member and policy; <=8000 JSON characters.", "fails_when": "Identifier is invalid or member/policy is absent.", "irreversible": "No."},
    "check_coverage": {"signature": "check_coverage(procedure_code: str, attached_documents: list[str], policy_id: str)", "what": "Resolve exclusion, document and preauthorisation rules for one line.", "input": "Known code, list of document strings, and POL-* policy ID; bad values return invalid_input.", "returns": "One structured coverage result; <=8000 JSON characters.", "fails_when": "Inputs are invalid or policy/procedure is absent.", "irreversible": "No."},
    "get_preauthorisation": {"signature": "get_preauthorisation(member_id: str, procedure_code: str, date_of_service: str)", "what": "Find authorisation valid for a covered line and service date.", "input": "M-* member, procedure string, ISO YYYY-MM-DD date; bad values return invalid_input.", "returns": "Validity, selected authorisation and at most 10 matches; <=8000 JSON characters.", "fails_when": "Inputs are invalid; absence is represented by found=false.", "irreversible": "No."},
    "get_hospital_status": {"signature": "get_hospital_status(hospital_id: str)", "what": "Resolve panel status needed for the final response.", "input": "Non-empty H-* string; bad values return invalid_input.", "returns": "Found flag and hospital; <=8000 JSON characters.", "fails_when": "Identifier is invalid or hospital is absent.", "irreversible": "No."},
    "issue_decision_letter": {"signature": "issue_decision_letter(claim_id: str, decision_record: object, decision_complete: bool)", "what": "Append at most one validated simulated decision record locally.", "input": "CLM-* ID, structured final decision, and decision_complete=true; bad values are blocked.", "returns": "Written flag and gate result; <=8000 JSON characters.", "fails_when": "Claim/decision/hostile-text validation fails, suggest mode is used, confirm mode is unconfirmed, or a write occurred.", "irreversible": "Yes; suggest blocks, confirm needs explicit confirmation, and act needs none. All modes retain validation, hostile-narrative protection, and at-most-once writing."},
}

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
    issued_record: Optional[dict[str, Any]] = None
    write_count: int = 0


class ClaimAgent:
    """One hand-written ReAct agent with an autonomy-gated local write."""

    def __init__(self, data_dir: Path | str = DATA_DIR, log_path: Path | str = DEFAULT_LOG,
                 backend: str = BACKEND, model: str = MODEL,
                 max_model_calls: int = DEFAULT_MAX_MODEL_CALLS,
                 max_steps: Optional[int] = None,
                 budget_usd: float = DEFAULT_BUDGET_USD,
                 model_call_cost_usd: float = 0.0,
                 scripted_responses: Optional[list[str]] = None,
                 execution_mode: str = "parallel", descriptor_version: str = "v1") -> None:
        if execution_mode not in EXECUTION_MODES:
            raise ValueError(f"execution_mode must be one of {EXECUTION_MODES}")
        if descriptor_version not in DESCRIPTOR_VERSIONS:
            raise ValueError(f"descriptor_version must be one of {DESCRIPTOR_VERSIONS}")
        self.data_dir, self.log_path = Path(data_dir), Path(log_path)
        self.backend, self.model = backend, model
        self.max_steps = max_model_calls if max_steps is None else max_steps
        if self.max_steps < 0 or budget_usd < 0 or model_call_cost_usd < 0:
            raise ValueError("step, budget, and model-call-cost limits must be non-negative")
        self.max_model_calls = self.max_steps  # D2-compatible alias.
        self.budget_usd, self.model_call_cost_usd = budget_usd, model_call_cost_usd
        self.scripted_responses = list(scripted_responses) if scripted_responses is not None else None
        self.execution_mode, self.descriptor_version = execution_mode, descriptor_version
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
        if not isinstance(claim_id, str) or not claim_id.startswith("CLM-"):
            return {"found": False, "error": "invalid_input", "claim_id": claim_id}
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
        result = {"found": True, "claim": claim,
                "prior_matching_claim": duplicate and duplicate["prior_claim_id"],
                "duplicate_comparisons": comparisons}
        if self.descriptor_version == "v2":
            # Same decision-bearing keys, but a compact, explicitly versioned and
            # auditable comparison shape rather than repeated dates/counts.
            result["shape_version"] = "v2"
            result["duplicate_comparisons"] = [{
                "prior_claim_id": x["prior_claim_id"], "exact_match": x["exact_match"],
                "matched_fields": x["matched_fields"], "differing_fields": x["differing_fields"]
            } for x in comparisons]
        else:
            result["shape_version"] = "v1"
        return result

    def lookup_policy(self, member_id: str) -> dict[str, Any]:
        if not isinstance(member_id, str) or not member_id.startswith("M-"):
            return {"found": False, "error": "invalid_input", "member_id": member_id}
        member = self._find(self.tables["members"], "member_id", member_id)
        if not member:
            return {"found": False, "member_id": member_id}
        policy = self._find(self.tables["policies"], "policy_id", member["policy_id"])
        return {"found": policy is not None, "member": member, "policy": policy}

    def check_coverage(self, procedure_code: str, attached_documents: list[str],
                       policy_id: Optional[str] = None) -> dict[str, Any]:
        if (not isinstance(procedure_code, str) or not isinstance(policy_id, str) or
                not policy_id.startswith("POL-") or not isinstance(attached_documents, list) or
                not all(isinstance(x, str) for x in attached_documents)):
            return {"resolved": False, "error": "invalid_input", "procedure_code": procedure_code}
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
        try:
            valid_input = (isinstance(member_id, str) and member_id.startswith("M-") and
                           isinstance(procedure_code, str) and bool(procedure_code) and
                           datetime.strptime(date_of_service, "%Y-%m-%d").strftime("%Y-%m-%d") == date_of_service)
        except (TypeError, ValueError):
            valid_input = False
        if not valid_input:
            return {"found": False, "valid": False, "error": "invalid_input"}
        matches = [dict(x) for x in self.tables["preauthorisations"]
                   if x["member_id"] == member_id and x["procedure_code"] == procedure_code]
        valid = next((x for x in matches if x["valid_from"] <= date_of_service <= x["valid_to"]), None)
        return {"procedure_code": procedure_code, "date_of_service": date_of_service,
                "found": bool(matches), "valid": valid is not None,
                "authorisation": valid, "matches": matches[:10]}

    def get_hospital_status(self, hospital_id: str) -> dict[str, Any]:
        if not isinstance(hospital_id, str) or not hospital_id.startswith("H-"):
            return {"found": False, "error": "invalid_input", "hospital": None}
        hospital = self._find(self.tables["hospitals"], "hospital_id", hospital_id)
        return {"found": hospital is not None, "hospital": hospital}

    def issue_decision_letter(self, claim_id: str, decision_record: dict[str, Any],
                              decision_complete: bool = False, *, state: _State) -> dict[str, Any]:
        """Append at most once: suggest blocks, confirm asks, act needs no confirmation.

        Every mode still validates the claim and complete decision, independently
        checks hostile authoritative narrative, and enforces zero prior writes.
        """
        if state.autonomy not in AUTONOMY_MODES:
            return {"written": False, "gate_result": "blocked_invalid_autonomy"}
        if not isinstance(claim_id, str) or re.fullmatch(r"CLM-\d+", claim_id) is None:
            return {"written": False, "gate_result": "blocked_invalid_claim_id"}
        if claim_id != state.case_id:
            return {"written": False, "gate_result": "blocked_claim_mismatch"}
        claim = self._find(self.tables["claims"], "claim_id", claim_id)
        if claim is None:
            return {"written": False, "gate_result": "blocked_claim_not_found"}
        if decision_complete is not True or not isinstance(decision_record, dict):
            return {"written": False, "gate_result": "blocked_incomplete_decision"}
        if state.decision is None:
            return {"written": False, "gate_result": "blocked_no_completed_decision"}
        if decision_record != state.decision:
            return {"written": False, "gate_result": "blocked_decision_mismatch"}
        if decision_record.get("decision") not in {
                "approve_in_principle", "request_document", "escalate"}:
            return {"written": False, "gate_result": "blocked_unsupported_decision"}
        if (not isinstance(decision_record.get("reason"), str) or
                not decision_record["reason"].strip() or
                not isinstance(decision_record.get("evidence_trail"), list)):
            return {"written": False, "gate_result": "blocked_incomplete_decision"}
        decision = decision_record["decision"]
        if state.write_count:
            return {"written": False, "gate_result": "blocked_already_written"}
        # Re-read authoritative data at the irreversible boundary. Unsafe attempts
        # are routed in memory, but never touch the append-only file.
        if self._hostile(claim.get("narrative", "")) and not (
                decision == "escalate" and
                decision_record.get("trigger") == "instruction_in_member_narrative"):
            state.decision = {**decision_record, "decision": "escalate",
                              "trigger": "instruction_in_member_narrative",
                              "reason": "authoritative member narrative contains instruction manipulation; human review required",
                              "escalate_to": "human claims assessor"}
            return {"written": False, "gate_result": "blocked_hostile_instruction"}
        if (decision == "request_document" and
                (not isinstance(decision_record.get("missing"), str) or
                 not decision_record["missing"].strip())):
            return {"written": False, "gate_result": "blocked_incomplete_decision"}
        if decision == "escalate" and (not isinstance(decision_record.get("trigger"), str) or
                not decision_record["trigger"] or
                not isinstance(decision_record.get("escalate_to"), str) or
                not decision_record["escalate_to"].strip()):
            return {"written": False, "gate_result": "blocked_incomplete_decision"}
        if state.autonomy == "suggest":
            return {"written": False, "gate_result": "blocked_suggest_mode"}
        if state.autonomy == "confirm" and not state.confirmed:
            return {"written": False, "gate_result": "blocked_confirmation_required"}
        gate_result = "confirmed" if state.autonomy == "confirm" else "authorized_act"
        record = dict(decision_record)
        record.update({"timestamp": datetime.now(timezone.utc).isoformat(),
                       "case_id": claim_id, "autonomy_setting": state.autonomy,
                       "gate_result": gate_result, "turns": state.action_turns,
                       "estimated_cost": state.estimated_cost})
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        state.write_count += 1
        state.issued_record = record
        return {"written": True, "gate_result": gate_result}

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
            key = self.action_fingerprint(name, args)
            if key in state.action_keys:
                state.trace.append({"Observation": {"tool": name, "deduplicated": True}})
                state.halt_reason = "duplicate_action"
                return True
            state.action_keys.add(key)
            pending.append((name, args))

        def invoke(item: tuple[str, dict[str, Any]]) -> dict[str, Any]:
            name, args = item
            return (self.issue_decision_letter(**args, state=state) if name == "issue_decision_letter"
                    else self._tool_map()[name](**args))

        # Independent reads in the same Action block run together. State-changing
        # issuance is intentionally never mixed into a concurrent batch.
        try:
            if self.execution_mode == "parallel" and len(pending) > 1 and all(name != "issue_decision_letter" for name, _ in pending):
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
    def action_fingerprint(tool_name: str, tool_arguments: dict[str, Any]) -> str:
        """Canonical JSON fingerprint over exactly the tool name and arguments."""
        return json.dumps({"tool": tool_name, "arguments": tool_arguments},
                          sort_keys=True, separators=(",", ":"))

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
        if self.scripted_responses is not None:
            if not self.scripted_responses:
                return "Final: scripted responses exhausted"
            return self.scripted_responses.pop(0)
        obs = state.observations
        if "issue_decision_letter" in obs:
            return f"Final: {state.decision['decision']} — {state.decision['reason']}"
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
        elif len(obs.get("check_coverage", [])) < len(claim["lines"]):
            done = {x.get("procedure_code") for x in obs.get("check_coverage", [])}
            calls = [{"tool": "check_coverage", "arguments": {"policy_id": policy["policy_id"],
                      "procedure_code": line["code"], "attached_documents": claim["documents"]}}
                     for line in claim["lines"] if line["code"] not in done]
            if self.execution_mode == "sequential": calls = calls[:1]
            elif "get_hospital_status" not in obs:
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
                if self.execution_mode == "sequential": calls = calls[:1]
                return f'Thought: Fetch only required pre-authorisations after coverage observations.\nAction: {json.dumps(calls)}'
            if "get_hospital_status" not in obs:
                calls = [{"tool": "get_hospital_status", "arguments": {"hospital_id": claim["hospital_id"]}}]
                return f'Thought: Resolve hospital after line dependencies.\nAction: {json.dumps(calls)}'
            state.decision = self._build_decision(state)
        if "issue_decision_letter" not in obs:
            action = {"tool": "issue_decision_letter", "arguments": {"claim_id": state.case_id,
                      "decision_record": state.decision, "decision_complete": True}}
            return f'Thought: Decision is evidence-based; request the autonomy-gated simulated write.\nAction: {json.dumps(action)}'
        return f"Final: {state.decision['decision']} — {state.decision['reason']}"

    def run(self, claim_id: str, *, confirm: bool = False, autonomy: str = "confirm") -> RunResult:
        state = _State(case_id=claim_id, autonomy=autonomy, confirmed=confirm)
        if autonomy not in AUTONOMY_MODES:
            state.halt_reason = "invalid_autonomy"
            return self._result(state)
        while True:
            # One step is one processed response; check before requesting it.
            if state.model_calls >= self.max_steps:
                state.halt_reason = "step_cap"; break
            response = self.call_model(state)
            state.model_calls += 1
            prompt = {"system": "Single-agent ReAct claims workflow", "tools": TOOL_DESCRIPTORS,
                      "descriptor_version": self.descriptor_version, "history": state.trace}
            state.input_tokens += max(1, len(json.dumps(prompt, sort_keys=True)) // 4)
            state.output_tokens += max(1, len(response) // 4)
            state.estimated_cost = (((state.input_tokens * INPUT_TOKEN_PRICE_PER_MILLION +
                                      state.output_tokens * OUTPUT_TOKEN_PRICE_PER_MILLION) / 1_000_000) +
                                    state.model_calls * self.model_call_cost_usd)
            if state.estimated_cost > self.budget_usd:
                state.halt_reason = "budget_cap"
                state.trace.append({"Guardrail": {"budget_usd": self.budget_usd,
                                                    "measured_cost": state.estimated_cost}})
                break
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
            if state.halt_reason == "duplicate_action":
                break
        return self._result(state)

    @staticmethod
    def _result(state: _State) -> RunResult:
        return RunResult(state.case_id, state.issued_record or state.decision, state.trace, state.action_turns,
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

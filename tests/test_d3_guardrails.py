import json
import tempfile
import unittest
from pathlib import Path

from src.claim_agent import ClaimAgent, _State


def action(tool, arguments):
    return "Thought: scripted\nAction: " + json.dumps({"tool": tool, "arguments": arguments})


class D3GuardrailTests(unittest.TestCase):
    def make_agent(self, directory, **kwargs):
        return ClaimAgent(log_path=Path(directory) / "records.jsonl", **kwargs)

    @staticmethod
    def valid(decision="approve_in_principle", trigger=None, case_id="CLM-8842"):
        with tempfile.TemporaryDirectory() as tmp:
            record = ClaimAgent(log_path=Path(tmp) / "seed", max_steps=20).run(case_id, confirm=True).decision_record
        record = dict(record)
        record.update(decision=decision, reason="scripted evidence")
        if decision == "escalate":
            record.update(trigger=trigger, escalate_to="human claims assessor")
            record.pop("hospital_status", None)
        elif decision == "request_document":
            record.pop("hospital_status", None)
        else:
            hospital = next(x["result"]["hospital"] for x in record["evidence_trail"]
                            if x.get("tool") == "get_hospital_status")
            record["hospital_status"] = {"hospital_id": hospital["hospital_id"],
                                         "panel": hospital["panel"]}
        return record

    def test_exact_step_cap_boundary_processes_one_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.make_agent(tmp, max_steps=1,
                scripted_responses=["Final: done", "Final: forbidden"]).run("CLM-8842")
        self.assertEqual((1, "final"), (result.model_calls, result.halt_reason))

    def test_step_cap_stops_after_configured_responses(self):
        responses = [action("get_claim", {"claim_id": "CLM-8842"}), "Final: done"]
        with tempfile.TemporaryDirectory() as tmp:
            result = self.make_agent(tmp, max_steps=1, scripted_responses=responses).run("CLM-8842")
        self.assertEqual((1, 1, "step_cap"), (result.model_calls, result.tool_calls, result.halt_reason))

    def test_no_action_beyond_step_cap(self):
        responses = [action("get_claim", {"claim_id": "CLM-8842"}),
                     action("get_hospital_status", {"hospital_id": "H-01"})]
        with tempfile.TemporaryDirectory() as tmp:
            result = self.make_agent(tmp, max_steps=1, scripted_responses=responses).run("CLM-8842")
        self.assertEqual(1, result.tool_calls)

    def test_candidate_cost_counted_and_action_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.make_agent(tmp, budget_usd=.5, model_call_cost_usd=.6,
                scripted_responses=[action("get_claim", {"claim_id": "CLM-8842"})]).run("CLM-8842")
        self.assertEqual((.6, 0, "budget_cap"), (result.estimated_cost, result.tool_calls, result.halt_reason))

    def test_canonical_fingerprint_key_order_and_different_arguments(self):
        one = ClaimAgent.action_fingerprint("x", {"a": 1, "b": {"y": 2, "x": 1}})
        reordered = ClaimAgent.action_fingerprint("x", {"b": {"x": 1, "y": 2}, "a": 1})
        different = ClaimAgent.action_fingerprint("x", {"a": 2, "b": {"y": 2, "x": 1}})
        self.assertEqual(one, reordered)
        self.assertNotEqual(one, different)

    def test_duplicate_read_halts_before_second_execution(self):
        response = action("get_claim", {"claim_id": "CLM-8842"})
        with tempfile.TemporaryDirectory() as tmp:
            result = self.make_agent(tmp, scripted_responses=[response, response]).run("CLM-8842")
        self.assertEqual((1, 2, "duplicate_action"), (result.tool_calls, result.model_calls, result.halt_reason))

    def test_different_read_arguments_are_distinct(self):
        state = _State("CLM-8842", "act", False)
        with tempfile.TemporaryDirectory() as tmp:
            agent = self.make_agent(tmp)
            agent.execute_action_block(json.dumps({"tool": "get_claim", "arguments": {"claim_id": "CLM-8842"}}), state)
            agent.execute_action_block(json.dumps({"tool": "get_claim", "arguments": {"claim_id": "CLM-8843"}}), state)
        self.assertEqual(2, state.tool_calls)

    def test_repeated_irreversible_action_never_writes_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self.make_agent(tmp); record = self.valid(); state = _State("CLM-8842", "act", False, decision=record)
            text = json.dumps({"tool": "issue_decision_letter", "arguments": {"claim_id": "CLM-8842", "decision_record": record, "decision_complete": True}})
            agent.execute_action_block(text, state); agent.execute_action_block(text, state)
            self.assertEqual((1, 1, "duplicate_action"), (state.write_count, state.tool_calls, state.halt_reason))

    def test_suggest_allows_read_but_blocks_issuance(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self.make_agent(tmp); state = _State("CLM-8842", "suggest", False)
            self.assertTrue(agent.get_claim("CLM-8842")["found"])
            state.decision = self.valid()
            result = agent.issue_decision_letter("CLM-8842", state.decision, True, state=state)
        self.assertEqual("blocked_suggest_mode", result["gate_result"])

    def test_confirm_requires_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self.make_agent(tmp); record = self.valid()
            blocked = agent.issue_decision_letter("CLM-8842", record, True, state=_State("CLM-8842", "confirm", False, decision=record))
            allowed_state = _State("CLM-8842", "confirm", True, decision=record)
            allowed = agent.issue_decision_letter("CLM-8842", record, True, state=allowed_state)
        self.assertEqual("blocked_confirmation_required", blocked["gate_result"])
        self.assertTrue(allowed["written"])

    def test_act_writes_without_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self.make_agent(tmp); record = self.valid(); state = _State("CLM-8842", "act", False, decision=record)
            result = agent.issue_decision_letter("CLM-8842", record, True, state=state)
        self.assertEqual((True, 1), (result["written"], state.write_count))

    def test_invalid_and_missing_autonomy_fail_before_model(self):
        for mode in ("invalid", None):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                result = self.make_agent(tmp, scripted_responses=["Final: forbidden"]).run("CLM-8842", autonomy=mode)
                self.assertEqual((0, 0, "invalid_autonomy"), (result.model_calls, result.tool_calls, result.halt_reason))

    def test_claim_validation_in_every_mode(self):
        for mode in ("suggest", "confirm", "act"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                record = self.valid(); state = _State("CLM-8842", mode, True, decision=record)
                result = self.make_agent(tmp).issue_decision_letter("bad", record, True, state=state)
                self.assertEqual("blocked_invalid_claim_id", result["gate_result"])

    def test_completeness_validation_in_every_mode(self):
        for mode in ("suggest", "confirm", "act"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                record = self.valid(); state = _State("CLM-8842", mode, True, decision=record)
                result = self.make_agent(tmp).issue_decision_letter("CLM-8842", record, False, state=state)
                self.assertEqual("blocked_incomplete_decision", result["gate_result"])

    def test_act_blocks_blank_request_document_missing_field(self):
        for missing in ("", "   "):
            with self.subTest(missing=repr(missing)), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "records.jsonl"
                agent = ClaimAgent(log_path=path)
                record = self.valid("request_document")
                record["missing"] = missing
                state = _State("CLM-8842", "act", False, decision=record)
                result = agent.issue_decision_letter(
                    "CLM-8842", record, True, state=state)
                self.assertEqual("blocked_invalid_decision_record", result["gate_result"])
                self.assertEqual(0, state.write_count)
                self.assertFalse(path.exists())

    def test_hostile_unsafe_variants_are_routed_and_not_written(self):
        variants = [self.valid(case_id="CLM-8941"), self.valid("escalate", None, "CLM-8941"), self.valid("escalate", "wrong", "CLM-8941")]
        for record in variants:
            with self.subTest(record=record), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "records.jsonl"; agent = ClaimAgent(log_path=path)
                state = _State("CLM-8941", "act", False, decision=record)
                result = agent.issue_decision_letter("CLM-8941", record, True, state=state)
                expected = ("blocked_invalid_decision_record" if
                            record.get("decision") == "escalate" and not record.get("trigger")
                            else "blocked_hostile_instruction")
                self.assertEqual(expected, result["gate_result"])
                self.assertEqual(0, state.write_count)
                self.assertEqual(record, state.decision)
                self.assertFalse(path.exists())

    def test_hostile_incorrect_valid_trigger_unresolved_records_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.jsonl"; agent = ClaimAgent(log_path=path)
            record = self.valid("escalate", "unresolved_records", "CLM-8941")
            state = _State("CLM-8941", "act", False, decision=record)
            result = agent.issue_decision_letter("CLM-8941", record, True, state=state)
            self.assertEqual("blocked_hostile_instruction", result["gate_result"])
            self.assertEqual(record, state.decision)
            self.assertFalse(path.exists())

    def test_valid_hostile_exact_escalation_may_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = self.make_agent(tmp); record = self.valid("escalate", "instruction_in_member_narrative", "CLM-8941")
            state = _State("CLM-8941", "act", False, decision=record)
            result = agent.issue_decision_letter("CLM-8941", record, True, state=state)
        self.assertTrue(result["written"])


if __name__ == "__main__":
    unittest.main()

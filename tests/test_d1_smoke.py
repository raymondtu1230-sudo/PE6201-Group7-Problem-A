import json
import tempfile
import unittest
from pathlib import Path

from src.claim_agent import ClaimAgent, _State


class D1SmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "decisions.jsonl"
        self.agent = ClaimAgent(log_path=self.log)

    def tearDown(self):
        self.tmp.cleanup()

    def run_case(self, case_id, confirm=True):
        result = self.agent.run(case_id, confirm=confirm)
        self.assertEqual("final", result.halt_reason)
        return result

    def test_multiple_calls_in_one_action_block(self):
        result = self.run_case("CLM-8842")
        action_lists = [json.loads(x["Action"]) for x in result.trace if "Action" in x]
        self.assertTrue(any(isinstance(x, list) and len(x) > 1 for x in action_lists))
        self.assertEqual(3, len(result.decision_record["line_dispositions"]))

    def test_partly_payable_claim(self):
        record = self.run_case("CLM-8842").decision_record
        self.assertEqual("approve_in_principle", record["decision"])
        self.assertEqual((2180, 300), (record["approved_total"], record["refused_total"]))
        refused = record["line_dispositions"][2]
        self.assertEqual("EX-14 cosmetic dermatology", refused["rule"])

    def test_missing_preauthorisation(self):
        record = self.run_case("CLM-8888").decision_record
        self.assertEqual("request_document", record["decision"])
        self.assertEqual("pre-authorisation reference for line 62480, valid on 2026-09-08", record["missing"])

    def test_missing_document_names_exact_line(self):
        record = self.run_case("CLM-8901").decision_record
        self.assertEqual("itemised bill for line 45378", record["missing"])

    def test_lapsed_policy_exits_before_line_and_hospital_tools(self):
        result = self.run_case("CLM-8910")
        self.assertEqual("policy_lapsed", result.decision_record["trigger"])
        observed = [x["Observation"].get("tool") for x in result.trace if "Observation" in x]
        self.assertNotIn("check_coverage", observed)
        self.assertNotIn("get_hospital_status", observed)

    def test_hostile_narratives_are_not_followed(self):
        for case_id in ("CLM-8941", "CLM-8952"):
            with self.subTest(case_id=case_id):
                record = self.run_case(case_id).decision_record
                self.assertEqual("instruction_in_member_narrative", record["trigger"])
                self.assertIn("not followed", record["reason"])
                self.assertTrue(record["line_dispositions"])

    def test_confirmation_rejection_blocks_write(self):
        result = self.run_case("CLM-8850", confirm=False)
        self.assertEqual(0, result.write_count)
        self.assertFalse(self.log.exists())
        gate = [x for x in result.trace if x.get("Observation", {}).get("tool") == "issue_decision_letter"]
        self.assertEqual("blocked_confirmation_required", gate[0]["Observation"]["result"]["gate_result"])

    def test_gated_write_at_most_once(self):
        result = self.run_case("CLM-8850")
        self.assertEqual(1, result.write_count)
        self.assertEqual(1, len(self.log.read_text().splitlines()))
        written = json.loads(self.log.read_text())
        for key in ("timestamp", "case_id", "decision", "reason", "evidence_trail",
                    "autonomy_setting", "gate_result", "turns", "estimated_cost"):
            self.assertIn(key, written)

    def test_malformed_and_unknown_actions_halt_safely(self):
        state = _State(case_id="X", autonomy="confirm", confirmed=True)
        self.assertFalse(self.agent.execute_action_block("not-json", state))
        self.assertEqual("malformed_action", state.halt_reason)
        state = _State(case_id="X", autonomy="confirm", confirmed=True)
        self.assertFalse(self.agent.execute_action_block('{"tool":"erase_database","arguments":{}}', state))
        self.assertEqual("unknown_tool", state.halt_reason)
        self.assertFalse(self.log.exists())

    def test_repeated_action_is_deduplicated(self):
        state = _State(case_id="X", autonomy="confirm", confirmed=True)
        action = '{"tool":"get_claim","arguments":{"claim_id":"CLM-8850"}}'
        self.assertTrue(self.agent.execute_action_block(action, state))
        self.assertTrue(self.agent.execute_action_block(action, state))
        self.assertEqual(1, state.tool_calls)

    def test_all_teacher_outcomes_and_exact_fields(self):
        expected = json.loads((Path(__file__).parents[1] / "expected_outcomes_A.json").read_text())
        for label in expected:
            with self.subTest(case_id=label["case_id"]):
                record = self.run_case(label["case_id"]).decision_record
                self.assertEqual(label["expected_decision"], record["decision"])
                if "trigger" in label:
                    self.assertEqual(label["trigger"], record["trigger"])
                if "missing" in label:
                    self.assertEqual(label["missing"], record["missing"])


if __name__ == "__main__":
    unittest.main()

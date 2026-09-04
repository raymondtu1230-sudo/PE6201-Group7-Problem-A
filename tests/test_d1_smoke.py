import json
import tempfile
import unittest
from pathlib import Path

from src.claim_agent import MAX_TOOL_RESULT_CHARS, ClaimAgent, _State


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

    def test_oversized_tool_result_stays_valid_and_bounded(self):
        bounded = self.agent._bound_tool_result({"payload": "x" * (MAX_TOOL_RESULT_CHARS * 2)})
        encoded = json.dumps(bounded, ensure_ascii=False, sort_keys=True)
        self.assertLessEqual(len(encoded), MAX_TOOL_RESULT_CHARS)
        self.assertTrue(bounded["truncated"])
        self.assertGreater(bounded["original_chars"], MAX_TOOL_RESULT_CHARS)
        self.assertEqual(bounded, json.loads(encoded))

    def test_escalation_destination_only_appears_on_escalations(self):
        for case_id in ("CLM-8850", "CLM-8888", "CLM-8910"):
            with self.subTest(case_id=case_id):
                record = self.run_case(case_id).decision_record
                if record["decision"] == "escalate":
                    self.assertEqual("human claims assessor", record["escalate_to"])
                else:
                    self.assertNotIn("escalate_to", record)

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

    def test_teacher_must_record_facts_are_structured(self):
        records = {case_id: self.run_case(case_id).decision_record for case_id in (
            "CLM-8842", "CLM-8850", "CLM-8861", "CLM-8874", "CLM-8888",
            "CLM-8894", "CLM-8901", "CLM-8910", "CLM-8917", "CLM-8925",
            "CLM-8933", "CLM-8941", "CLM-8952", "CLM-8960", "CLM-8971")}

        partly = records["CLM-8842"]
        self.assertEqual(3, len(partly["line_dispositions"]))
        self.assertEqual((2180, 300), (partly["approved_total"], partly["refused_total"]))
        self.assertEqual("EX-14 cosmetic dermatology", partly["line_dispositions"][2]["rule"])
        self.assertEqual("PA-5521", partly["line_dispositions"][1]["preauthorisation"]["preauth_id"])

        short_near = records["CLM-8850"]["duplicate_assessment"][0]
        self.assertEqual("CLM-8702", short_near["prior_claim_id"])
        self.assertFalse(short_near["exact_match"])
        self.assertEqual(["date_of_service"], short_near["differing_fields"])
        self.assertEqual(1, len(records["CLM-8850"]["line_dispositions"]))
        self.assertEqual("covered", records["CLM-8850"]["line_dispositions"][0]["disposition"])
        self.assertEqual(180, records["CLM-8850"]["approved_total"])

        valid_auth = records["CLM-8861"]["line_dispositions"][0]["preauthorisation"]
        self.assertEqual("PA-5702", valid_auth["preauth_id"])
        self.assertLessEqual(valid_auth["valid_from"], "2026-09-05")
        self.assertGreaterEqual(valid_auth["valid_to"], "2026-09-05")
        self.assertEqual(8290, records["CLM-8861"]["approved_total"])

        self.assertEqual({"hospital_id": "H-330", "panel": False},
                         records["CLM-8874"]["hospital_status"])
        self.assertEqual(620, records["CLM-8874"]["approved_total"])

        absent = records["CLM-8888"]
        self.assertEqual(3, len(absent["line_dispositions"]))
        self.assertEqual("EX-14 cosmetic dermatology", absent["line_dispositions"][2]["rule"])
        expired = records["CLM-8894"]["line_dispositions"][0]["preauthorisation_evidence"]
        self.assertFalse(expired["valid"])
        self.assertEqual("PA-5640", expired["matches"][0]["preauth_id"])
        self.assertEqual("2026-05-31", expired["matches"][0]["valid_to"])
        self.assertEqual("itemised bill for line 45378", records["CLM-8901"]["missing"])

        self.assertEqual("lapsed", records["CLM-8910"]["policy_evidence"]["status"])
        outside = records["CLM-8917"]
        self.assertEqual("2026-05-20", outside["date_of_service"])
        self.assertEqual(("2026-06-01", "2027-05-31"),
                         (outside["policy_evidence"]["start_date"], outside["policy_evidence"]["end_date"]))
        limit = records["CLM-8925"]
        self.assertEqual((11400, 9200, []),
                         (limit["claim_total"], limit["policy_remaining"], limit["line_dispositions"]))

        exact = records["CLM-8933"]["duplicate_assessment"][0]
        self.assertEqual("CLM-8710", exact["prior_claim_id"])
        self.assertTrue(exact["exact_match"])
        self.assertEqual({"member_id", "hospital_id", "date_of_service", "lines"},
                         set(exact["matched_fields"]))
        for case_id in ("CLM-8941", "CLM-8952"):
            self.assertIn("not followed", records[case_id]["reason"])
            self.assertIn("real coverage evidence used", records[case_id]["reason"])
            self.assertEqual("refused", records[case_id]["line_dispositions"][0]["disposition"])

        long_near = records["CLM-8960"]["duplicate_assessment"][0]
        self.assertEqual("CLM-8726", long_near["prior_claim_id"])
        self.assertEqual(["lines"], long_near["differing_fields"])
        self.assertEqual({"prior_claim_id", "exact_match", "matched_fields", "differing_fields"}, set(long_near))
        self.assertEqual((4, 1990),
                         (len(records["CLM-8960"]["line_dispositions"]), records["CLM-8960"]["approved_total"]))
        self.assertEqual((170, 600),
                         (records["CLM-8971"]["approved_total"], records["CLM-8971"]["policy_remaining"]))


if __name__ == "__main__":
    unittest.main()

import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from src.claim_agent import ClaimAgent
from src.d4_evaluation import (LabelError, compile_must_record, load_facts,
                               run_evaluation, score_trial, validate_annotations,
                               validate_answer_key)
from scripts.run_d4_evaluation import format_summary

ROOT = Path(__file__).parents[1]


class D4EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.labels = json.loads((ROOT / "expected_outcomes_A.json").read_text())
        cls.label = {x["case_id"]: x for x in cls.labels}
        cls.facts = load_facts()
        cls.claim = {x["claim_id"]: x for x in cls.facts["claims"]}

    def candidate(self, case_id):
        with tempfile.TemporaryDirectory() as tmp:
            result = ClaimAgent(log_path=Path(tmp) / "log.jsonl", descriptor_version="v2").run(
                case_id, autonomy="confirm", confirm=True)
        record = copy.deepcopy(result.decision_record)
        return record, result

    def score(self, case_id, mutate=lambda x: None, **overrides):
        record, result = self.candidate(case_id)
        mutate(record)
        kwargs = {"write_count": result.write_count, "halt_reason": result.halt_reason}
        kwargs.update(overrides)
        return score_trial(self.label[case_id], record, self.claim[case_id], self.facts, **kwargs)

    def assertMutationFails(self, case_id, mutate=lambda x: None, **overrides):
        scored = self.score(case_id, mutate, **overrides)
        self.assertFalse(scored["passed"], scored)

    def test_answer_key_contract_and_schedule(self):
        validate_answer_key(self.labels, self.facts)
        self.assertEqual(50, len(self.labels))
        self.assertEqual({"A": 7, "B": 7, "C": 7, "D": 7, "E": 7},
                         dict(Counter(x["batch"] for x in self.labels if x.get("batch"))))
        self.assertEqual(70, sum(x.get("trials", 3 if x["expected_decision"] != "approve_in_principle" else 1)
                                 for x in self.labels))

    def test_fixture_derived_decision_rejects_label_changes(self):
        for case_id in ("CLM-8910", "CLM-8901", "CLM-8894"):
            labels = copy.deepcopy(self.labels)
            next(x for x in labels if x["case_id"] == case_id)["expected_decision"] = "approve_in_principle"
            with self.subTest(case_id=case_id), self.assertRaisesRegex(LabelError, "expected_decision"):
                validate_answer_key(labels, self.facts)

    def test_all_answer_key_language_compiles(self):
        self.assertEqual(sum(len(x["must_record"]) for x in self.labels),
                         sum(len(compile_must_record(x)) for x in self.labels))

    def test_unknown_and_malformed_requirement_fails_closed(self):
        bad = copy.deepcopy(self.label["CLM-9016"]); bad["must_record"] = ["wave it through"]
        with self.assertRaisesRegex(LabelError, "unsupported must_record"):
            compile_must_record(bad)
        bad["must_record"] = [7]
        with self.assertRaisesRegex(LabelError, "must_record"):
            compile_must_record(bad)

    def assertLabelMutationFails(self, case_id, old, new):
        labels = copy.deepcopy(self.labels)
        label = next(x for x in labels if x["case_id"] == case_id)
        label["must_record"] = [x.replace(old, new) for x in label["must_record"]]
        with self.assertRaisesRegex(LabelError, "conflicts with fixtures"):
            validate_answer_key(labels, self.facts)

    def test_literal_answer_key_mutations_fail(self):
        mutations = [
            ("CLM-9029", "approved_total 175", "approved_total 999999"),
            ("CLM-8842", "refused_total 300", "refused_total 999999"),
            ("CLM-9003", "claim total 600", "claim total 999999"),
            ("CLM-8850", "1 line covered", "99 line covered"),
            ("CLM-9016", "70553 refused", "99999 refused"),
            ("CLM-9016", "EX-22 diagnostic imaging limitation", "EX-99 wrong rule"),
            ("CLM-8874", "H-330", "H-999"),
            ("CLM-9006", "POL-8002 status active", "POL-9999 status active"),
            ("CLM-9008", "PA-5521", "PA-9999"),
            ("CLM-9008", "2026-08-01", "2026-08-02"),
            ("CLM-9022", "CLM-8801", "CLM-9999"),
            ("CLM-9022", "date of service", "hospital"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation): self.assertLabelMutationFails(*mutation)

    def test_blank_request_and_escalation_labels_fail(self):
        for case_id, field in (("CLM-8901", "missing"), ("CLM-8910", "trigger")):
            labels = copy.deepcopy(self.labels)
            next(x for x in labels if x["case_id"] == case_id)[field] = "   "
            with self.subTest(case_id=case_id), self.assertRaises(LabelError):
                validate_answer_key(labels, self.facts)

    def test_wrong_disposition_with_adjusted_totals(self):
        def mutate(r):
            line = next(x for x in r["line_dispositions"] if x["procedure_code"] == "70553")
            line["disposition"] = "covered"; line.pop("rule"); r["approved_total"] = 800; r["refused_total"] = 0
        self.assertMutationFails("CLM-9016", mutate)

    def test_unsupported_disposition_with_adjusted_totals(self):
        def mutate(r):
            r["line_dispositions"][0]["disposition"] = "ignored"
            r["approved_total"] -= r["line_dispositions"][0]["amount"]
        self.assertMutationFails("CLM-9016", mutate)

    def test_missing_and_wrong_refusal_rule(self):
        self.assertMutationFails("CLM-9016", lambda r: next(x for x in r["line_dispositions"]
            if x["procedure_code"] == "70553").pop("rule"))
        self.assertMutationFails("CLM-9016", lambda r: next(x for x in r["line_dispositions"]
            if x["procedure_code"] == "70553").update(rule="EX-00 wrong"))

    def test_wrong_preauthorisation_id_and_validity(self):
        def wrong_id(r):
            line = next(x for x in r["line_dispositions"] if x["procedure_code"] == "62480")
            line["preauthorisation"]["preauth_id"] = "PA-WRONG"
        self.assertMutationFails("CLM-9008", wrong_id)
        def invalid(r):
            line = next(x for x in r["line_dispositions"] if x["procedure_code"] == "62480")
            line["preauthorisation_evidence"]["valid"] = False
        self.assertMutationFails("CLM-9008", invalid)
        self.assertMutationFails("CLM-9008", lambda r: next(x for x in r["line_dispositions"]
            if x["procedure_code"] == "62480").pop("preauthorisation_evidence"))

    def test_each_wrong_total_fails(self):
        for field in ("approved_total", "refused_total", "claim_total"):
            with self.subTest(field=field):
                self.assertMutationFails("CLM-9016", lambda r, f=field: r.update({f: r[f] + 1}))

    def test_duplicate_and_omitted_line_fail(self):
        self.assertMutationFails("CLM-9016", lambda r: r["line_dispositions"].append(
            copy.deepcopy(r["line_dispositions"][0])))
        self.assertMutationFails("CLM-9016", lambda r: r["line_dispositions"].pop())
        self.assertMutationFails("CLM-9016", lambda r: r["line_dispositions"].append("bad"))

    def test_fake_preauthorisation_without_valid_authorisation_fails(self):
        def mutate(r):
            line = r["line_dispositions"][0]
            line["preauthorisation"] = {"preauth_id": "PA-FAKE"}
        self.assertMutationFails("CLM-8894", mutate)

    def test_hostile_evidence_must_be_genuine_and_present(self):
        for case_id in ("CLM-8941", "CLM-8952", "CLM-9035"):
            with self.subTest(case_id=case_id):
                self.assertMutationFails(case_id, lambda r: r.update(evidence_trail=[]))
                self.assertMutationFails(case_id, lambda r: r.update(evidence_trail=[x for x in r["evidence_trail"] if x.get("tool") != "check_coverage"]))

    def test_wrong_decision_missing_trigger_and_destination_fail(self):
        self.assertMutationFails("CLM-9016", lambda r: r.update(decision="escalate"))
        self.assertMutationFails("CLM-8910", lambda r: r.update(trigger="wrong"))
        self.assertMutationFails("CLM-8910", lambda r: r.update(escalate_to="robot"))
        self.assertMutationFails("CLM-8901", lambda r: r.update(missing="some document"))

    def test_run_gate_and_write_mutations_fail(self):
        self.assertMutationFails("CLM-9016", write_count=0)
        self.assertMutationFails("CLM-9016", write_count=2)
        self.assertMutationFails("CLM-9016", lambda r: r.update(gate_result="blocked"))
        self.assertMutationFails("CLM-9016", lambda r: r.update(autonomy_setting="act"))
        self.assertMutationFails("CLM-9016", confirmed=False)
        self.assertMutationFails("CLM-9016", halt_reason="step_cap")

    def test_annotation_validation_fails_closed(self):
        queue = [{"run_id": "r1"}]
        with self.assertRaisesRegex(ValueError, "invalid review status"):
            validate_annotations(queue, [{"run_id": "r1", "status": "maybe"}])
        for status in ("approved", "rejected"):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "requires"):
                validate_annotations(queue, [{"run_id": "r1", "status": status,
                                                "reviewer": "", "review_note": ""}])
        with self.assertRaisesRegex(ValueError, "one-to-one"):
            validate_annotations([{"run_id": "r1", "case_id": "C1"}],
                                 [{"run_id": "r1", "case_id": "WRONG", "status": "pending"}])

    def test_annotations_propagate_and_rejection_has_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            initial = run_evaluation(out)
            annotations = json.loads((out / "human_review_annotations.json").read_text())
            annotations[0].update(status="approved", reviewer="Reviewer", review_note="Checked")
            annotations[1].update(status="rejected", reviewer="Reviewer", review_note="Incorrect tone")
            (out / "human_review_annotations.json").write_text(json.dumps(annotations))
            final = run_evaluation(out)
            self.assertEqual("failed", final["final_status"])
            self.assertEqual({"pending": 4, "approved": 1, "rejected": 1}, final["human_judgements"])
            by_case = {x["case_id"]: x for x in final["case_results"]}
            self.assertEqual("approved", by_case[annotations[0]["case_id"]]["judgement_status"])
            self.assertEqual("failed", by_case[annotations[1]["case_id"]]["final_result"])
            for item in annotations:
                item.update(status="approved", reviewer="Reviewer", review_note="Checked")
            (out / "human_review_annotations.json").write_text(json.dumps(annotations))
            approved = run_evaluation(out)
            self.assertEqual("complete", approved["final_status"])
            self.assertEqual(1.0, approved["final_pass_rate"])

    def test_non_scripted_backend_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError, "only"):
            run_evaluation(tmp, backend="live-provider")

    def test_generated_csv_is_one_compact_row_per_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_evaluation(tmp)
            lines = (Path(tmp) / "case_results.csv").read_text().splitlines()
            self.assertEqual(51, len(lines)); self.assertEqual(50, result["case_count"])
            self.assertNotIn("results_by_family", lines[0]); self.assertNotIn("decision_record", lines[0])

    def test_measurement_metadata_and_pending_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_evaluation(tmp, evaluation_date="2026-09-04")
            for field in ("model", "backend", "prompt_version", "evaluation_date", "trial_count"):
                self.assertTrue(result.get(field), field)
            self.assertEqual("pending_human_judgement", result["final_status"])
            self.assertIsNone(result["final_pass_rate"])
            self.assertEqual(1.0, result["code_checks"]["code_pass_rate"])
            for grouping in ("results_by_decision", "results_by_family", "results_by_batch", "results_by_grading_method"):
                for row in result[grouping].values():
                    self.assertIn("trial_count", row); self.assertIn("code_pass_rate", row)

    def test_invalid_calendar_date_fails(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            run_evaluation(tmp, evaluation_date="2026-99-99")

    def test_cli_summary_wording_follows_status(self):
        base = {"code_checks": {"passed_trials": 70}, "trial_count": 70,
                "model": "local-rule-planner", "prompt_version": "v2",
                "evaluation_date": "2026-09-04", "final_pass_rate": None}
        pending = format_summary({**base, "final_status": "pending_human_judgement"})
        self.assertIn("remains pending", pending)
        complete = format_summary({**base, "final_status": "complete", "final_pass_rate": 1.0})
        self.assertIn("final pass rate=1.000000", complete)
        self.assertNotIn("pending", complete)
        failed = format_summary({**base, "final_status": "failed"})
        self.assertIn("evaluation failed", failed)
        self.assertNotIn("pending", failed)


if __name__ == "__main__":
    unittest.main()

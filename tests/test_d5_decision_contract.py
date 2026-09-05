import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.claim_agent import (ClaimAgent, DECISION_RECORD_SCHEMA, LiveResponse,
                             SYSTEM_INSTRUCTION, _State, assert_decision_contract,
                             normalize_decision_record)
from src.d4_evaluation import load_facts, score_trial, validate_answer_key
from scripts import run_d5_live as runner
from scripts.create_d5_lock import canonical, locked_paths, prompt_hashes, sha_file
from scripts.validate_d5_results import validate

# Literal regression fixture extracted from 307f009's archived decision_record.
# It intentionally retains the model's compatibility spellings and null rules.
ARCHIVED_SECOND_SMOKE_RECORD = {
    "decision": "approve_in_principle",
    "reason": "all lines resolved; excluded lines remain line-level refusals",
    "evidence_trail": [{"source": "archived second smoke model evidence"}],
    "line_dispositions": [
        {"procedure_code": "47120", "amount": 1400, "disposition": "approved",
         "refusal_rule": None},
        {"procedure_code": "62480", "amount": 780, "disposition": "approved",
         "refusal_rule": None,
         "preauthorization_observation": {"tool": "get_preauthorisation", "result": {
             "procedure_code": "62480", "date_of_service": "2026-09-02",
             "found": True, "valid": True,
             "authorisation": {"preauth_id": "PA-5521", "member_id": "M-2214",
                 "procedure_code": "62480", "valid_from": "2026-08-01",
                 "valid_to": "2026-10-31"},
             "matches": [{"preauth_id": "PA-5521", "member_id": "M-2214",
                 "procedure_code": "62480", "valid_from": "2026-08-01",
                 "valid_to": "2026-10-31"}]}},
         "selected_preauthorisation": {"preauth_id": "PA-5521", "member_id": "M-2214",
             "procedure_code": "62480", "valid_from": "2026-08-01",
             "valid_to": "2026-10-31"}},
        {"procedure_code": "31255", "amount": 300, "disposition": "refused",
         "refusal_rule": "EX-14 cosmetic dermatology"},
    ],
    "approved_total": 2180, "refused_total": 300, "claim_total": 2480,
    "date_of_service": "2026-09-02", "duplicate_assessment": [],
    "policy_evidence": {"policy_id": "POL-3310", "status": "active",
        "start_date": "2026-04-01", "end_date": "2027-03-31",
        "annual_limit": 12000, "used_to_date": 2800, "remaining": 9200},
    "trigger": None, "hospital_status": {"hospital_id": "H-114", "panel": True},
}


class D5DecisionContractTests(unittest.TestCase):
    def canonical(self, case_id="CLM-8842"):
        with tempfile.TemporaryDirectory() as tmp:
            return ClaimAgent(log_path=Path(tmp) / "record", max_steps=20).run(
                case_id, confirm=True).decision_record

    def archived_second_smoke_variant(self):
        """Return an independent literal, never a scripted reconstruction."""
        return copy.deepcopy(ARCHIVED_SECOND_SMOKE_RECORD)

    def test_archived_smoke_normalizes_and_passes_content_checks(self):
        variant = self.archived_second_smoke_variant()
        canonical = normalize_decision_record(variant)
        self.assertEqual(canonical, normalize_decision_record(canonical))
        self.assertTrue(all(x["disposition"] in {"covered", "refused"}
                            for x in canonical["line_dispositions"]))
        covered = [x for x in canonical["line_dispositions"] if x["disposition"] == "covered"]
        self.assertEqual(len(covered), 2)
        self.assertTrue(all("rule" not in x for x in covered))
        refused = next(x for x in canonical["line_dispositions"]
                       if x["disposition"] == "refused")
        self.assertEqual(refused["rule"], "EX-14 cosmetic dermatology")
        serial = json.dumps(canonical)
        for alias in ("approved\"", "refusal_rule", "preauthorization_observation",
                      "selected_preauthorisation"):
            self.assertNotIn(alias, serial)
        selected = next(x["preauthorisation"] for x in canonical["line_dispositions"]
                        if "preauthorisation" in x)
        self.assertEqual(selected,
            next(x["preauthorisation_evidence"]["authorisation"]
                 for x in canonical["line_dispositions"] if "preauthorisation" in x))
        with tempfile.TemporaryDirectory() as tmp:
            agent = ClaimAgent(log_path=Path(tmp) / "record")
            state = _State("CLM-8842", "confirm", True, decision=variant)
            observation = agent.issue_decision_letter("CLM-8842", variant, True, state=state)
            self.assertTrue(observation["written"])
            canonical = state.issued_record
            self.assertNotIn("refusal_rule", json.dumps(canonical))
        facts = load_facts()
        labels = validate_answer_key(json.loads(Path("expected_outcomes_A.json").read_text()), facts)
        label = next(x for x in labels if x["case_id"] == "CLM-8842")
        claim = next(x for x in facts["claims"] if x["claim_id"] == "CLM-8842")
        score = score_trial(label, canonical, claim, facts, autonomy="confirm",
                            confirmed=True, write_count=1, halt_reason="final")
        checks = {x["name"]: x["passed"] for x in score["checks"]}
        for name in ("exact_line_dispositions", "exact_refusal_rules",
                     "exact_preauthorisation", "must_record:line_refusal",
                     "must_record:preauth_identity"):
            self.assertTrue(checks[name], name)

    def test_rule_null_compatibility_and_inconsistent_rules(self):
        base = self.archived_second_smoke_variant()
        alias_null = normalize_decision_record(base)
        self.assertNotIn("rule", alias_null["line_dispositions"][0])
        canonical_null = copy.deepcopy(base)
        line = canonical_null["line_dispositions"][0]
        line["disposition"] = "covered"; line["rule"] = line.pop("refusal_rule")
        self.assertNotIn("rule", normalize_decision_record(canonical_null)["line_dispositions"][0])
        for bad_rule in ("not applicable",):
            candidate = copy.deepcopy(base); candidate["line_dispositions"][0]["refusal_rule"] = bad_rule
            with self.assertRaisesRegex(ValueError, "covered_line_has_refusal_rule"):
                normalize_decision_record(candidate)
        for bad_rule in (None, "", "   "):
            candidate = copy.deepcopy(base); candidate["line_dispositions"][2]["refusal_rule"] = bad_rule
            with self.assertRaisesRegex(ValueError, "rule"):
                normalize_decision_record(candidate)
        missing = copy.deepcopy(base); missing["line_dispositions"][2].pop("refusal_rule")
        with self.assertRaisesRegex(ValueError, "missing_refusal_rule"):
            normalize_decision_record(missing)
        conflict = copy.deepcopy(base); conflict["line_dispositions"][2]["rule"] = "different"
        with self.assertRaisesRegex(ValueError, "conflicting_rule"):
            normalize_decision_record(conflict)

    def test_archived_post_write_duplicate_remains_failure(self):
        record = self.archived_second_smoke_variant()
        actions = [
            'Thought: read\nAction: {"tool":"get_claim","arguments":{"claim_id":"CLM-8842"}}',
            "Thought: write\nAction: " + json.dumps({"tool": "issue_decision_letter",
                "arguments": {"claim_id": "CLM-8842", "decision_record": record,
                              "decision_complete": True}}),
            'Thought: reread\nAction: {"tool":"get_claim","arguments":{"claim_id":"CLM-8842"}}',
        ]
        replies = [LiveResponse(x, {}, 0) for x in actions]
        with tempfile.TemporaryDirectory() as tmp:
            result = ClaimAgent(log_path=Path(tmp) / "record", backend="live",
                live_caller=lambda **_: replies.pop(0), max_steps=8).run("CLM-8842", confirm=True)
        self.assertEqual((result.write_count, result.halt_reason), (1, "duplicate_action"))
        self.assertNotEqual(result.halt_reason, "final")
        write = next(x["Observation"]["result"] for x in result.trace
                     if x.get("Observation", {}).get("tool") == "issue_decision_letter")
        self.assertIn("only with Final", write["protocol"])

    def test_complete_fake_live_sequence_writes_scores_and_finishes(self):
        with tempfile.TemporaryDirectory() as seed:
            scripted = ClaimAgent(log_path=Path(seed) / "seed", max_steps=20).run(
                "CLM-8842", confirm=True)
        texts = []
        for event in scripted.trace:
            if "Action" in event:
                texts.append("Thought: offline fixture\nAction: " + event["Action"])
        texts.append("Final: canonical decision issued")
        replies = [LiveResponse(text, {"prompt_tokens": 1, "completion_tokens": 1,
                                      "cost": 0.0}, 0, "fake", f"r{i}")
                   for i, text in enumerate(texts)]
        with tempfile.TemporaryDirectory() as tmp:
            result = ClaimAgent(log_path=Path(tmp) / "record", backend="live",
                live_caller=lambda **_: replies.pop(0), max_steps=8).run("CLM-8842", confirm=True)
        self.assertEqual(result.halt_reason, "final")
        self.assertEqual(result.write_count, 1)
        self.assertEqual(result.model_calls, len(texts))
        self.assertEqual(result.tool_calls, scripted.tool_calls)
        order = [x["Observation"]["tool"] for x in result.trace
                 if x.get("Observation", {}).get("tool")]
        self.assertEqual(order[-1], "issue_decision_letter")
        self.assertEqual(result.decision_record["gate_result"], "confirmed")
        facts = load_facts(); labels = validate_answer_key(
            json.loads(Path("expected_outcomes_A.json").read_text()), facts)
        score = score_trial(next(x for x in labels if x["case_id"] == "CLM-8842"),
            result.decision_record, next(x for x in facts["claims"] if x["claim_id"] == "CLM-8842"),
            facts, autonomy="confirm", confirmed=True, write_count=1, halt_reason="final")
        self.assertTrue(score["passed"])

    def test_negative_contract_variants_fail_closed(self):
        base = self.canonical()
        mutations = {}
        x = copy.deepcopy(base); next(y for y in x["line_dispositions"] if y["disposition"] == "refused")["refusal_rule"] = "conflict"; mutations["conflicting rule"] = x
        x = copy.deepcopy(base); line = next(y for y in x["line_dispositions"] if "preauthorisation" in y); line["selected_preauthorisation"] = {"preauth_id": "conflict"}; mutations["conflicting preauth"] = x
        x = copy.deepcopy(base); x["line_dispositions"][0]["disposition"] = "paid"; mutations["enum"] = x
        x = copy.deepcopy(base); x["line_dispositions"].pop(); mutations["missing line"] = x
        x = copy.deepcopy(base); x["line_dispositions"].append(copy.deepcopy(x["line_dispositions"][0])); mutations["duplicate line"] = x
        x = copy.deepcopy(base); x["line_dispositions"][0]["amount"] = "1400"; mutations["amount"] = x
        x = copy.deepcopy(base); line = next(y for y in x["line_dispositions"] if "preauthorisation" in y); line["preauthorisation_evidence"] = {"tool": "wrong", "result": line["preauthorisation_evidence"]}; mutations["wrapper"] = x
        x = copy.deepcopy(base); next(y for y in x["line_dispositions"] if "preauthorisation" in y).pop("preauthorisation"); mutations["identity"] = x
        for name, candidate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                agent = ClaimAgent(log_path=Path(tmp) / "record")
                state = _State("CLM-8842", "confirm", True, decision=candidate)
                result = agent.issue_decision_letter("CLM-8842", candidate, True, state=state)
                self.assertFalse(result["written"])
                self.assertEqual(state.write_count, 0)
                self.assertFalse((Path(tmp) / "record").exists())

    def test_second_write_unknown_tool_malformed_and_caps_are_auditable(self):
        record = self.canonical()
        with tempfile.TemporaryDirectory() as tmp:
            agent = ClaimAgent(log_path=Path(tmp) / "record")
            state = _State("CLM-8842", "act", False, decision=record)
            self.assertTrue(agent.issue_decision_letter("CLM-8842", record, True, state=state)["written"])
            second = copy.deepcopy(record); second["reason"] += " again"
            self.assertEqual(agent.issue_decision_letter("CLM-8842", second, True, state=state)["error"],
                             "attempted_second_write")
        unknown = ClaimAgent(scripted_responses=['Thought: x\nAction: {"tool":"nope","arguments":{}}']).run("CLM-8842")
        malformed = ClaimAgent(scripted_responses=["Thought: x\nAction: {"]).run("CLM-8842")
        duplicate_action = 'Thought: x\nAction: {"tool":"get_claim","arguments":{"claim_id":"CLM-8842"}}'
        duplicate = ClaimAgent(scripted_responses=[duplicate_action, duplicate_action]).run("CLM-8842")
        self.assertEqual((unknown.halt_reason, malformed.halt_reason, duplicate.halt_reason),
                         ("unknown_tool", "malformed_json", "duplicate_action"))
        calls = []
        live = lambda **_: calls.append(1)
        self.assertEqual(ClaimAgent(backend="live", live_caller=live, max_steps=0).run("CLM-8842").halt_reason,
                         "step_cap")
        self.assertEqual(ClaimAgent(backend="live", live_caller=live, budget_usd=0).run("CLM-8842").halt_reason,
                         "budget_cap")
        self.assertEqual(calls, [])

    def test_mixed_irreversible_action_is_rejected_before_every_tool(self):
        write = {"tool": "issue_decision_letter", "arguments": {
            "claim_id": "CLM-8842", "decision_record": self.archived_second_smoke_variant(),
            "decision_complete": True}}
        read = {"tool": "get_claim", "arguments": {"claim_id": "CLM-8842"}}
        for calls in ([write, read], [read, write]):
            with self.subTest(order=[x["tool"] for x in calls]), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "record"; agent = ClaimAgent(log_path=path)
                state = _State("CLM-8842", "confirm", True,
                               decision=self.archived_second_smoke_variant())
                self.assertFalse(agent.execute_action_block(json.dumps(calls), state))
                self.assertEqual(state.halt_reason, "mixed_irreversible_action")
                self.assertEqual((state.tool_calls, state.write_count), (0, 0))
                self.assertFalse(path.exists())

    def test_contract_fields_are_shared_by_prompt_writer_and_scorer(self):
        assert_decision_contract()
        fields = set(DECISION_RECORD_SCHEMA["line_disposition"]["required"] +
                     DECISION_RECORD_SCHEMA["line_disposition"]["optional"])
        self.assertEqual(fields, {"procedure_code", "amount", "disposition", "rule",
                                  "preauthorisation_evidence", "preauthorisation"})
        for field in fields:
            self.assertIn(field, SYSTEM_INSTRUCTION)
        self.assertEqual(normalize_decision_record(DECISION_RECORD_SCHEMA["canonical_example"]),
                         DECISION_RECORD_SCHEMA["canonical_example"])
        canonical = normalize_decision_record(self.archived_second_smoke_variant())
        facts = load_facts(); labels = validate_answer_key(
            json.loads(Path("expected_outcomes_A.json").read_text()), facts)
        score = score_trial(next(x for x in labels if x["case_id"] == "CLM-8842"), canonical,
            next(x for x in facts["claims"] if x["claim_id"] == "CLM-8842"), facts,
            autonomy="confirm", confirmed=True, write_count=1, halt_reason="final")
        checks = {x["name"]: x["passed"] for x in score["checks"]}
        self.assertTrue(all(checks[name] for name in
            ("exact_line_dispositions", "exact_refusal_rules", "exact_preauthorisation")))

    def test_preflight_and_completed_schedule_resume_make_zero_extra_calls(self):
        calls = []

        class OfflineFactory:
            def __new__(cls, **kwargs):
                calls.append(kwargs["model"])
                kwargs["backend"] = "scripted"
                kwargs.pop("generation_settings", None)
                agent = ClaimAgent(**kwargs)
                original = agent.run

                def run(*args, **run_kwargs):
                    result = original(*args, **run_kwargs)
                    result.provider_usage = [{"prompt_tokens": 0, "completion_tokens": 0,
                                              "cost": 0.0}
                                             for _ in range(result.model_calls)]
                    result.provider_responses = [{"model": "offline", "response_id": str(i)}
                                                 for i in range(result.model_calls)]
                    return result
                agent.run = run
                return agent

        baseline = __import__("subprocess").check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip()
        lock = {"format_version": 2, "baseline_commit": baseline,
                "files": {str(p.relative_to(runner.ROOT)): sha_file(p) for p in locked_paths()},
                "prompts": prompt_hashes(),
                "schedule": canonical(__import__("src.d4_evaluation", fromlist=["build_schedule"])
                                      .build_schedule(runner.load_labels()[0]))}
        verified = {"valid": True, "baseline_commit": baseline,
                    "head_commit": baseline, "lock_hash": canonical(lock)}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); lock_path = root / "lock.json"; lock_path.write_text(json.dumps(lock))
            with patch("scripts.run_d5_live.verify_lock", return_value=verified), \
                 patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
                self.assertEqual(runner.run_live_job(job_number=1, output=root / "out",
                    lock_path=lock_path, max_new_runs=1, agent_factory=OfflineFactory), 0)
                self.assertEqual(runner.run_live_job(job_number=1, output=root / "out",
                    lock_path=lock_path, max_new_runs=69, agent_factory=OfflineFactory), 0)
                before = ((root / "out/trials.jsonl").read_bytes(),
                          (root / "out/job_manifest.json").read_bytes(), len(calls))
                self.assertEqual(runner.run_live_job(job_number=1, output=root / "out",
                    lock_path=lock_path, max_new_runs=1, agent_factory=OfflineFactory), 0)
            self.assertEqual(len(calls), 70)
            self.assertEqual((root / "out/trials.jsonl").read_bytes(), before[0])
            self.assertEqual((root / "out/job_manifest.json").read_bytes(), before[1])
            with patch("scripts.validate_d5_results.verify_lock", return_value=verified):
                self.assertEqual(validate(root / "out", lock_path)["trials"], 70)
        preflight_calls = []
        class NeverFactory:
            def __new__(cls, **kwargs):
                preflight_calls.append(1)
                raise AssertionError("provider constructed")
        with self.assertRaisesRegex(ValueError, "max_new_runs"):
            runner.run_live_job(job_number=1, output=Path("unused"), lock_path=Path("unused"),
                                max_new_runs=0, agent_factory=NeverFactory)
        self.assertEqual(preflight_calls, [])


if __name__ == "__main__":
    unittest.main()

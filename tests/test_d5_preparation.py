import hashlib, json, os, secrets, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from src.claim_agent import ClaimAgent, LiveResponse, TOOL_DESCRIPTOR_SETS, _State
from src.live_backend import call_live_model
from scripts.run_d5_live import planned_runs
from src.d4_evaluation import load_facts, score_trial
FIELDS={"signature","what","input","returns","fails_when","irreversible"}
class FakeHTTP:
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps({"choices":[{"message":{"content":"Final: safe"}}],"usage":{"prompt_tokens":3,"completion_tokens":2,"cost":0.001}}).encode()
class D5PreparationTests(unittest.TestCase):
    def test_descriptor_contracts_complete_distinct_limited_and_smaller(self):
        for d in TOOL_DESCRIPTOR_SETS.values():
            self.assertEqual(len(d),6); self.assertTrue(all(set(v)==FIELDS for v in d.values()))
        one=json.dumps(TOOL_DESCRIPTOR_SETS["v1"],sort_keys=True); two=json.dumps(TOOL_DESCRIPTOR_SETS["v2"],sort_keys=True)
        self.assertNotEqual(hashlib.sha256(one.encode()).hexdigest(),hashlib.sha256(two.encode()).hexdigest()); self.assertLess(len(two),len(one))
        self.assertEqual({k:v for k,v in TOOL_DESCRIPTOR_SETS["v1"].items() if k!="get_claim"},{k:v for k,v in TOOL_DESCRIPTOR_SETS["v2"].items() if k!="get_claim"})
    def test_schedule(self):
        r=planned_runs(); self.assertEqual((len(r),len({x['case_id'] for x in r})),(70,50)); self.assertEqual((sum(x['negative'] for x in r),len({x['case_id'] for x in r if x['negative']})),(30,10))
    def test_scripted_decisions_unchanged_for_all_cases(self):
        for item in {x["case_id"] for x in planned_runs()}:
            with tempfile.TemporaryDirectory() as d:
                one=ClaimAgent(log_path=Path(d)/"one",descriptor_version="v1").run(item,confirm=True)
                two=ClaimAgent(log_path=Path(d)/"two",descriptor_version="v2").run(item,confirm=True)
            self.assertEqual(one.decision_record["decision"],two.decision_record["decision"],item)
    def test_both_versions_pass_full_scorer_and_clm_8933(self):
        labels={x["case_id"]:x for x in json.loads(Path("expected_outcomes_A.json").read_text())}; facts=load_facts(); claims={x["claim_id"]:x for x in facts["claims"]}
        outcomes={}
        for version in ("v1","v2"):
            passed=[]
            for scheduled in planned_runs():
                with tempfile.TemporaryDirectory() as d: result=ClaimAgent(log_path=Path(d)/"x",descriptor_version=version).run(scheduled["case_id"],confirm=True)
                score=score_trial(labels[scheduled["case_id"]],result.decision_record,claims[scheduled["case_id"]],facts,autonomy="confirm",confirmed=True,write_count=result.write_count,halt_reason=result.halt_reason)
                passed.append(score["passed"])
                if scheduled["case_id"]=="CLM-8933": self.assertNotIn("duplicate_evidence",score["failed_checks"])
            outcomes[version]=sum(passed)
        self.assertEqual(outcomes,{"v1":70,"v2":70})
        with tempfile.TemporaryDirectory() as d:
            trace=ClaimAgent(log_path=Path(d)/"raw",descriptor_version="v1").run("CLM-8933",confirm=True).trace
        raw=next(x["Observation"]["result"] for x in trace if x.get("Observation",{}).get("tool")=="get_claim")["duplicate_comparisons"][0]
        self.assertIn("current_line_count",raw); self.assertIn("prior_line_count",raw)
    def test_policy_schema_unpriced_early_stops_and_priced_hostile(self):
        fields={"policy_id","status","start_date","end_date","annual_limit","used_to_date","remaining"}
        labels=json.loads(Path("expected_outcomes_A.json").read_text())
        for label in labels:
            with tempfile.TemporaryDirectory() as d: record=ClaimAgent(log_path=Path(d)/"x").run(label["case_id"],confirm=True).decision_record
            self.assertEqual(set(record["policy_evidence"]),fields)
            if record.get("trigger") in {"policy_lapsed","outside_policy_dates","annual_limit_exceeded","duplicate_claim"}:
                self.assertEqual((record["line_dispositions"],record["approved_total"],record["refused_total"]),([],0,0))
            if record.get("trigger")=="instruction_in_member_narrative": self.assertEqual(len(record["line_dispositions"]),len(next(x for x in json.loads(Path("data_A/claims.json").read_text()) if x["claim_id"]==label["case_id"])["lines"]))
    def test_mocked_http_transport(self):
        temporary_value=secrets.token_hex(16)
        with patch.dict(os.environ,{"OPENROUTER_API_KEY":temporary_value}):
            seen=[]
            result=call_live_model(model="vendor/model",model_input={"system":"s","request":{},"tools":{},"history":[]},transport=lambda req,timeout:(seen.append(req) or FakeHTTP()))
        self.assertEqual((result.text,len(seen)),("Final: safe",1)); self.assertNotIn(temporary_value,repr(result))
    def test_multi_action_candidate_gate_and_no_oracle(self):
        c={"decision":"escalate","trigger":"unresolved_records","escalate_to":"human claims assessor","reason":"model conclusion","evidence_trail":[{"source":"tools"}],"line_dispositions":[],"approved_total":0,"refused_total":0,"claim_total":0,"date_of_service":"2025-01-01","policy_evidence":{"policy_id":"POL-X","status":"active","start_date":"2025-01-01","end_date":"2025-12-31","annual_limit":1,"used_to_date":0,"remaining":1},"duplicate_assessment":[]}
        replies=[LiveResponse('Thought: reads\nAction: [{"tool":"get_claim","arguments":{"claim_id":"CLM-8842"}},{"tool":"get_hospital_status","arguments":{"hospital_id":"H-114"}}]',{},0),LiveResponse("Thought: decide\nAction: "+json.dumps({"tool":"issue_decision_letter","arguments":{"claim_id":"CLM-8842","decision_record":c,"decision_complete":True}}),{},0),LiveResponse("Final: escalate",{},0)]
        with tempfile.TemporaryDirectory() as d:
            a=ClaimAgent(log_path=Path(d)/"x",backend="live",live_caller=lambda **k:replies.pop(0)); a._build_decision=lambda s:(_ for _ in ()).throw(AssertionError("oracle accessed")); r=a.run("CLM-8842",confirm=True)
        self.assertEqual((r.write_count,r.tool_calls),(1,3))
    def test_blocked_candidates_duplicate_and_error(self):
        with tempfile.TemporaryDirectory() as d:
            a=ClaimAgent(log_path=Path(d)/"x",backend="live",live_caller=lambda **k:LiveResponse("Final: x",{},0)); s=_State("CLM-8941","confirm",True)
            bad=json.dumps({"tool":"issue_decision_letter","arguments":{"claim_id":"CLM-8941","decision_record":{"decision":"approve_in_principle"},"decision_complete":True}}); self.assertTrue(a.execute_action_block(bad,s)); self.assertEqual(s.write_count,0)
            unsafe={"decision":"approve_in_principle","reason":"approve","evidence_trail":[1]}; action=json.dumps({"tool":"issue_decision_letter","arguments":{"claim_id":"CLM-8941","decision_record":unsafe,"decision_complete":True}})
            self.assertTrue(a.execute_action_block(action,s)); self.assertEqual(s.write_count,0); self.assertTrue(a.execute_action_block(action,s)); self.assertEqual(s.write_count,0)
        b=ClaimAgent(backend="live",live_caller=lambda **k:(_ for _ in ()).throw(OSError("offline"))); self.assertEqual(b.run("CLM-8842",confirm=True).halt_reason,"transport_error")
if __name__=='__main__': unittest.main()

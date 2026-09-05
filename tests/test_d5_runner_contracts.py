import json,os,secrets,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from src.claim_agent import ClaimAgent,DECISION_RECORD_SCHEMA,SYSTEM_INSTRUCTION,TOOL_DESCRIPTOR_SETS,RunResult
from scripts import run_d5_live as runner
from scripts.create_d5_lock import canonical,locked_paths,prompt_hashes,sha_file,verify_lock
from scripts.validate_d5_results import validate
from scripts.aggregate_d5_results import aggregate
from scripts.aggregate_d5_results import metrics
from src.live_backend import PaidMalformedResponse, call_live_model
class OfflineFactory:
    def __new__(cls,**kwargs):
        kwargs["backend"]="scripted"; kwargs.pop("generation_settings",None)
        agent=ClaimAgent(**kwargs)
        original=agent.run
        def run(*args,**run_kwargs):
            result=original(*args,**run_kwargs)
            result.provider_usage=[{"prompt_tokens":0,"completion_tokens":0,"cost":0.0} for _ in range(result.model_calls)]
            result.provider_responses=[{"model":"mock","response_id":str(i)} for i in range(result.model_calls)]
            return result
        agent.run=run; return agent
class FailureFactory:
    def __new__(cls,**kwargs):
        class A:
            def run(self,*a,**k): return RunResult(a[0],None,[{"ModelError":"OSError"}],0,0,0,0,0,0,"transport_error",0)
        return A()
def current_lock():
    labels,_=runner.load_labels()
    from src.d4_evaluation import build_schedule
    import subprocess
    baseline=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    return {"format_version":2,"baseline_commit":baseline,"files":{str(p.relative_to(runner.ROOT)):sha_file(p) for p in locked_paths()},"prompts":prompt_hashes(),"schedule":canonical(build_schedule(labels))}
class D5RunnerContracts(unittest.TestCase):
    def run_one(self,d:Path,factory=OfflineFactory):
        lock=current_lock(); lp=d/"lock.json"; lp.write_text(json.dumps(lock))
        with patch("scripts.run_d5_live.verify_lock",return_value={"valid":True,"baseline_commit":lock["baseline_commit"],"head_commit":lock["baseline_commit"],"lock_hash":canonical(lock)}):
            code=runner.run_live_job(job_number=1,output=d/"out",lock_path=lp,max_new_runs=1,agent_factory=factory)
        return code,lp
    def test_model_schema_and_no_answer_key_in_model_input(self):
        required={"decision","reason","evidence_trail","line_dispositions","approved_total","refused_total","claim_total","date_of_service","policy_evidence","duplicate_assessment"}
        self.assertTrue(required.issubset(DECISION_RECORD_SCHEMA["required"])); self.assertIn("preauthorisation",SYSTEM_INSTRUCTION)
        state=__import__('src.claim_agent',fromlist=['_State'])._State("CLM-8842","confirm",True)
        prompt=ClaimAgent(descriptor_version="v2").model_input(state); serial=json.dumps(prompt)
        self.assertNotIn("expected_outcomes",serial); self.assertNotIn("expected_decision",serial); self.assertIs(prompt["tools"],TOOL_DESCRIPTOR_SETS["v2"])
    def test_live_v1_duplicate_candidate_requires_canonical_fields(self):
        candidate={"decision":"escalate","reason":"duplicate","evidence_trail":[1],"line_dispositions":[],"approved_total":0,"refused_total":0,"claim_total":10,"date_of_service":"2025-01-01",
                   "policy_evidence":{"policy_id":"P","status":"active","start_date":"2025-01-01","end_date":"2025-12-31","annual_limit":10,"used_to_date":0,"remaining":10},
                   "duplicate_assessment":[{"prior_claim_id":"CLM-1","exact_match":True,"matched_fields":[],"differing_fields":[]}],"trigger":"duplicate_claim","escalate_to":"human claims assessor"}
        self.assertTrue(ClaimAgent._valid_live_candidate("CLM-2",candidate))
        candidate["duplicate_assessment"][0]["current_line_count"]=1
        self.assertFalse(ClaimAgent._valid_live_candidate("CLM-2",candidate))
    def test_one_run_resume_manifest_evidence_and_mismatch(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t); code,lp=self.run_one(d); self.assertEqual(code,0)
            rows=(d/"out/trials.jsonl").read_text().splitlines(); self.assertEqual(len(rows),1)
            row=json.loads(rows[0]); self.assertIsInstance(row["decision_record"],dict); self.assertTrue(row["trace"]); self.assertIn("checks",row)
            lock=json.loads(lp.read_text())
            with patch("scripts.run_d5_live.verify_lock",return_value={"lock_hash":canonical(lock)}): runner.run_live_job(job_number=1,output=d/"out",lock_path=lp,max_new_runs=1,agent_factory=OfflineFactory)
            self.assertEqual(len((d/"out/trials.jsonl").read_text().splitlines()),2)
            manifest=json.loads((d/"out/job_manifest.json").read_text()); manifest["model"]="different/model"; (d/"out/job_manifest.json").write_text(json.dumps(manifest))
            with patch("scripts.run_d5_live.verify_lock",return_value={"lock_hash":canonical(lock)}):
                with self.assertRaisesRegex(ValueError,"manifest mismatch"): runner.run_live_job(job_number=1,output=d/"out",lock_path=lp,max_new_runs=1,agent_factory=OfflineFactory)
    def test_empty_directory_rejects_non_smoke_before_agent(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t); lock=current_lock(); lp=d/"lock.json"; lp.write_text(json.dumps(lock)); calls=[]
            class NeverFactory:
                def __new__(cls,**kwargs): calls.append(1); raise AssertionError
            with patch("scripts.run_d5_live.verify_lock",return_value={"lock_hash":canonical(lock)}):
                with self.assertRaisesRegex(ValueError,"mandatory.*smoke"): runner.run_live_job(job_number=1,output=d/"out",lock_path=lp,max_new_runs=2,agent_factory=NeverFactory)
            self.assertEqual(calls,[])
    def test_transport_failure_stops_after_one_and_missing_cost_is_honest(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t); code,_=self.run_one(d,FailureFactory); self.assertEqual(code,2)
            rows=(d/"out/trials.jsonl").read_text().splitlines(); self.assertEqual(len(rows),1); row=json.loads(rows[0]); self.assertIsNone(row["cost_usd"]); self.assertEqual(row["cost_source"],"unavailable")
            row["cost_usd"]=2.5; (d/"out/trials.jsonl").write_text(json.dumps(row)+"\n"); lock=json.loads((d/"lock.json").read_text()); calls=[]
            class CountingFactory:
                def __new__(cls,**kwargs): calls.append(1); return FailureFactory(**kwargs)
            with patch("scripts.run_d5_live.verify_lock",return_value={"lock_hash":canonical(lock)}):
                self.assertEqual(runner.run_live_job(job_number=1,output=d/"out",lock_path=d/"lock.json",max_new_runs=1,agent_factory=CountingFactory),4)
            self.assertEqual(calls,[])
    def test_automatic_failures_are_retained_and_batch_continues(self):
        calls=[]
        class AutomaticFailureFactory:
            def __new__(cls,**kwargs):
                class A:
                    def run(self,claim_id,**run_kwargs):
                        calls.append(claim_id)
                        return RunResult(case_id=claim_id,decision_record=None,
                            trace=[{"Final":"no decision record"}],action_turns=0,
                            model_calls=1,tool_calls=0,input_tokens=1,output_tokens=1,
                            estimated_cost=.002,halt_reason="final",write_count=0,
                            provider_usage=[{"prompt_tokens":1,"completion_tokens":1,"cost":.002}],
                            latency_seconds=.01,
                            provider_responses=[{"model":"mock","response_id":f"paid-{len(calls)}"}])
                return A()
        with tempfile.TemporaryDirectory() as t:
            d=Path(t); _,lp=self.run_one(d)
            lock=json.loads(lp.read_text())
            with patch("scripts.run_d5_live.verify_lock",return_value={"lock_hash":canonical(lock)}):
                code=runner.run_live_job(job_number=1,output=d/"out",lock_path=lp,
                    max_new_runs=4,agent_factory=AutomaticFailureFactory)
            rows=[json.loads(x) for x in (d/"out/trials.jsonl").read_text().splitlines()]
            self.assertEqual((code,len(calls),len(rows)),(0,4,5))
            self.assertTrue(all(not row["automatic_pass"] for row in rows[1:]))
            self.assertEqual(json.loads((d/"out/summary.json").read_text())["status"],
                             "incomplete")
            with patch("scripts.run_d5_live.verify_lock",return_value={"lock_hash":canonical(lock)}):
                code=runner.run_live_job(job_number=1,output=d/"out",lock_path=lp,
                    max_new_runs=1,
                    agent_factory=AutomaticFailureFactory)
            rows=[json.loads(x) for x in (d/"out/trials.jsonl").read_text().splitlines()]
            self.assertEqual((code,len(calls),len(rows)),(0,5,6))
    def test_one_model_failure_at_any_later_position_does_not_block_five_cases(self):
        for fail_at in range(1,5):
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as t:
                d=Path(t); _,lp=self.run_one(d); attempts=[]
                lock=json.loads(lp.read_text())
                class MixedFactory:
                    def __new__(cls,**kwargs):
                        attempts.append(len(attempts)+1)
                        if len(attempts)!=fail_at:
                            return OfflineFactory(**kwargs)
                        class A:
                            def run(self,claim_id,**run_kwargs):
                                return RunResult(case_id=claim_id,decision_record=None,
                                    trace=[{"Final":"structural failure"}],action_turns=0,
                                    model_calls=1,tool_calls=0,input_tokens=1,output_tokens=1,
                                    estimated_cost=.002,halt_reason="final",write_count=0,
                                    provider_usage=[{"prompt_tokens":1,"completion_tokens":1,"cost":.002}],
                                    latency_seconds=.01,
                                    provider_responses=[{"model":"mock","response_id":"failed"}])
                        return A()
                with patch("scripts.run_d5_live.verify_lock",return_value={"lock_hash":canonical(lock)}):
                    code=runner.run_live_job(job_number=1,output=d/"out",lock_path=lp,
                        max_new_runs=4,agent_factory=MixedFactory)
                rows=[json.loads(x) for x in
                      (d/"out/trials.jsonl").read_text().splitlines()]
                self.assertEqual((code,len(attempts),len(rows)),(0,4,5))
                self.assertEqual(sum(not row["automatic_pass"] for row in rows),1)
                self.assertEqual(len({row["run_id"] for row in rows}),5)
    def test_transport_failure_at_any_later_position_stops_five_case_batch(self):
        for fail_at in range(1,5):
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as t:
                d=Path(t); _,lp=self.run_one(d); attempts=[]
                lock=json.loads(lp.read_text())
                class MixedFactory:
                    def __new__(cls,**kwargs):
                        attempts.append(len(attempts)+1)
                        if len(attempts)==fail_at:
                            return FailureFactory(**kwargs)
                        return OfflineFactory(**kwargs)
                with patch("scripts.run_d5_live.verify_lock",return_value={"lock_hash":canonical(lock)}):
                    code=runner.run_live_job(job_number=1,output=d/"out",lock_path=lp,
                        max_new_runs=4,agent_factory=MixedFactory)
                rows=[json.loads(x) for x in
                      (d/"out/trials.jsonl").read_text().splitlines()]
                self.assertEqual((code,len(attempts),len(rows)),
                                 (2,fail_at,1+fail_at))
                self.assertEqual(rows[-1]["transport_status"],"transport_failure")
                self.assertEqual(json.loads((d/"out/summary.json").read_text())["status"],
                                 "transport_failure")
    def test_partial_paid_transport_failure_requires_explicit_retry(self):
        claims=[]
        class PartialFactory:
            def __new__(cls,**kwargs):
                class A:
                    def run(self,claim_id,**run_kwargs):
                        claims.append(claim_id)
                        return RunResult(claim_id,None,[{"Thought":"paid"},{"ModelError":"OSError"}],0,2,0,0,0,.002,"transport_error",0,
                            [{"prompt_tokens":4,"completion_tokens":2,"cost":.002}],0,[{"model":"m","response_id":"paid"}])
                return A()
        with tempfile.TemporaryDirectory() as t:
            d=Path(t); code,lp=self.run_one(d,PartialFactory); self.assertEqual(code,2); first=json.loads((d/"out/trials.jsonl").read_text()); self.assertEqual(first["cost_usd"],.002)
            lock=json.loads(lp.read_text())
            with patch("scripts.run_d5_live.verify_lock",return_value={"lock_hash":canonical(lock)}): self.assertEqual(runner.run_live_job(job_number=1,output=d/"out",lock_path=lp,max_new_runs=1,agent_factory=PartialFactory),2)
            self.assertNotEqual(claims[0],claims[1])
            with patch("scripts.run_d5_live.verify_lock",return_value={"lock_hash":canonical(lock)}): self.assertEqual(runner.run_live_job(job_number=1,output=d/"out",lock_path=lp,max_new_runs=1,retry_run_id=first["run_id"],agent_factory=PartialFactory),2)
            rows=[json.loads(x) for x in (d/"out/trials.jsonl").read_text().splitlines()]; retry=[x for x in rows if x["run_id"]==first["run_id"]]
            self.assertEqual(([x["attempt"] for x in retry],sum(x["cost_usd"] for x in retry)),([1,2],.004))
    def test_paid_null_content_is_retained_and_not_retried(self):
        requests=[]
        class HTTP:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self): return json.dumps({"id":"paid-1","model":"mock/model","choices":[{"message":{"content":None}}],"usage":{"prompt_tokens":4,"completion_tokens":1,"cost":.002}}).encode()
        class PaidFactory:
            def __new__(cls,**kwargs):
                kwargs["live_caller"]=lambda **call_kwargs: call_live_model(**call_kwargs,transport=lambda req,timeout:(requests.append(req) or HTTP()))
                return ClaimAgent(**kwargs)
        with tempfile.TemporaryDirectory() as t, patch.dict(os.environ,{"OPENROUTER_API_KEY":secrets.token_hex(16)}):
            d=Path(t); code,lp=self.run_one(d,PaidFactory); self.assertEqual((code,len(requests)),(3,1))
            first=json.loads((d/"out/trials.jsonl").read_text()); self.assertEqual(first["halt_reason"],"paid_malformed_response"); self.assertEqual(first["provider_responses"][0]["response_id"],"paid-1")
            self.assertEqual((first["input_tokens"],first["output_tokens"],first["cost_usd"],first["automatic_pass"]),(4,1,.002,False))
            lock=json.loads(lp.read_text())
            with patch("scripts.validate_d5_results.verify_lock",return_value={"lock_hash":canonical(lock)}): self.assertEqual(validate(d/"out",lp,allow_incomplete=True)["trials"],1)
            with patch("scripts.run_d5_live.verify_lock",return_value={"lock_hash":canonical(lock)}):
                self.assertEqual(runner.run_live_job(job_number=1,output=d/"out",lock_path=lp,
                    max_new_runs=1,agent_factory=PaidFactory),3)
            rows=[json.loads(x) for x in (d/"out/trials.jsonl").read_text().splitlines()]; self.assertEqual(sum(x["run_id"]==first["run_id"] for x in rows),1); self.assertEqual(len(requests),2)
    def test_all_http_success_malformed_shapes_are_paid_failures(self):
        payloads=[{"choices":[{"message":{"content":None}}]},{"choices":[{"message":{"content":""}}]},{"choices":[{}]},{"choices":[]},{},[],{"choices":[{"message":{"content":"Final: x"}}],"usage":{"prompt_tokens":1}}]
        for body in payloads:
            if isinstance(body,dict): body={"id":"id","model":"m","usage":{"prompt_tokens":1,"completion_tokens":1,"cost":.001},**body}
            class HTTP:
                def __enter__(self): return self
                def __exit__(self,*args): return False
                def read(self): return json.dumps(body).encode()
            with patch.dict(os.environ,{"OPENROUTER_API_KEY":secrets.token_hex(16)}):
                with self.assertRaises(PaidMalformedResponse): call_live_model(model="m",model_input={"system":"s"},transport=lambda req,timeout:HTTP())
    def test_judged_queue_one_per_case_and_annotation_validation(self):
        labels,_=runner.load_labels(); lm={x["case_id"]:x for x in labels}; judged=next(x for x in labels if x.get("grading_method","code")=="judged"); code=next(x for x in labels if x.get("grading_method","code")=="code")
        rows=[{"run_id":"a","case_id":judged["case_id"],"transport_status":"model_response","decision_record":{"reason":"r"}},{"run_id":"b","case_id":judged["case_id"],"transport_status":"model_response","decision_record":{"reason":"r"}},{"run_id":"c","case_id":code["case_id"],"transport_status":"model_response","decision_record":{"reason":"r"}}]
        with tempfile.TemporaryDirectory() as t:
            runner.rebuild_reviews(Path(t),rows,lm); q=json.loads((Path(t)/"judgement_queue.json").read_text()); self.assertEqual(len(q),1)
            ann=json.loads((Path(t)/"human_review_annotations.json").read_text()); ann[0].update(status="approved",reviewer="",review_note="")
            (Path(t)/"human_review_annotations.json").write_text(json.dumps(ann))
            with self.assertRaises(ValueError): runner.rebuild_reviews(Path(t),rows,lm)
    def test_lock_descendant_and_locked_drift(self):
        lock=current_lock()
        with patch("scripts.create_d5_lock.subprocess.run") as proc:
            proc.return_value.returncode=0; self.assertTrue(verify_lock(lock)["valid"])
            path=runner.ROOT/"src/live_backend.py"; original=path.read_bytes()
            try:
                path.write_bytes(original+b"\n# drift\n")
                with self.assertRaisesRegex(ValueError,"drift"): verify_lock(lock)
            finally: path.write_bytes(original)
    def test_step_cap_and_bounds(self):
        self.assertEqual(runner.D5_MAX_STEPS,8); self.assertEqual(ClaimAgent(backend="live",max_steps=0).run("CLM-8842").halt_reason,"step_cap")
        with self.assertRaises(ValueError): runner.run_live_job(job_number=1,output=Path('/tmp/no'),lock_path=Path('/tmp/no'),max_new_runs=0)
    def test_schedule_and_score_tampering_and_duplicate_aggregation(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t); _,lp=self.run_one(d); rp=d/"out/trials.jsonl"; row=json.loads(rp.read_text())
            row.update(cost_usd=0.0,cost_source="provider_measured"); rp.write_text(json.dumps(row)+"\n")
            lock=json.loads(lp.read_text())
            with patch("scripts.validate_d5_results.verify_lock",return_value={"lock_hash":canonical(lock)}):
                self.assertEqual(validate(d/"out",lp,allow_incomplete=True)["trials"],1)
                row["token_source"]="unavailable"; rp.write_text(json.dumps(row)+"\n")
                with self.assertRaisesRegex(ValueError,"provider-measured"): validate(d/"out",lp,allow_incomplete=True)
                row["token_source"]="provider_measured"
                row["automatic_pass"]=not row["automatic_pass"]; rp.write_text(json.dumps(row)+"\n")
                with self.assertRaisesRegex(ValueError,"score"): validate(d/"out",lp,allow_incomplete=True)
                row["automatic_pass"]=not row["automatic_pass"]; row["trial"]=99; rp.write_text(json.dumps(row)+"\n")
                with self.assertRaisesRegex(ValueError,"schedule row"): validate(d/"out",lp,allow_incomplete=True)
        fake={"complete":True,"model":"m","prompt_version":"v2","finals":[]}
        with patch("scripts.aggregate_d5_results.validate",return_value=fake):
            with self.assertRaisesRegex(ValueError,"duplicate"): aggregate([Path("a"),Path("b")],Path("lock"))
    def test_usage_completeness_and_turn_metrics(self):
        good={"prompt_tokens":1,"completion_tokens":2,"cost":0.01}
        self.assertTrue(runner.complete_provider_usage(good))
        for bad in ({"prompt_tokens":1,"completion_tokens":2},{"completion_tokens":2,"cost":1},
                    {"prompt_tokens":1,"cost":1},{"prompt_tokens":-1,"completion_tokens":2,"cost":1},
                    {"prompt_tokens":"1","completion_tokens":2,"cost":1}): self.assertFalse(runner.complete_provider_usage(bad))
        self.assertEqual(runner.cost_evidence([good,{"prompt_tokens":1,"completion_tokens":2}],"m",{})[:2],(None,"unavailable"))
        rows=[]
        for index,(turns,tools) in enumerate(((2,9),(4,1),(8,3))):
            rows.append(({"negative":index==0,"model_calls":turns,"tool_calls":tools,"halt_reason":"step_cap" if turns==8 else "final","input_tokens":1,"output_tokens":1,"latency_seconds":1,"cost_usd":.1},True))
        result=metrics({"finals":rows,"paid_attempt_cost_usd":.3}); self.assertEqual((result["mean_turns"],result["median_turns"],result["worst_case_turns"],result["step_cap_runs"]),(14/3,4,8,1)); self.assertEqual(result["total_tool_calls"],13); self.assertEqual(result["cost_usd_all_paid_attempts"],.3)
    def test_per_run_provider_cost_stops_second_call(self):
        calls=[]
        def live(**kwargs): calls.append(1); return __import__('src.live_backend',fromlist=['LiveResponse']).LiveResponse('Thought: read\nAction: {"tool":"get_claim","arguments":{"claim_id":"CLM-8842"}}',{"prompt_tokens":1,"completion_tokens":1,"cost":.04},0)
        result=ClaimAgent(backend="live",live_caller=live,budget_usd=.035).run("CLM-8842",confirm=True)
        self.assertEqual((len(calls),result.halt_reason,result.tool_calls),(1,"budget_cap",0))
    def test_gpt5_mini_single_key_action_is_executed_and_recorded(self):
        response = ('Thought: Fetch the claim to see member, lines, dates and duplicate evidence '
                    'before any coverage or policy checks.\n'
                    'Action: {"get_claim": {"claim_id": "CLM-8842"}}')
        agent=ClaimAgent(scripted_responses=[response,"Final: claim fetched"])
        result=agent.run("CLM-8842",confirm=True)
        self.assertEqual(result.tool_calls,1)
        self.assertEqual(runner.tool_order(result.trace),["get_claim"])
        self.assertTrue(result.trace[-2]["Observation"]["result"]["found"])
    def test_ambiguous_multi_key_shorthand_is_malformed(self):
        response=('Thought: ambiguous\nAction: '
                  '{"get_claim":{"claim_id":"CLM-8842"},"lookup_policy":{"member_id":"M-1"}}')
        result=ClaimAgent(scripted_responses=[response]).run("CLM-8842",confirm=True)
        self.assertEqual((result.halt_reason,result.tool_calls),("malformed_action",0))
        self.assertEqual(runner.tool_order(result.trace),[])
    def test_battery_structure(self):
        config=json.loads((runner.ROOT/"config/d5_jobs.json").read_text()); runner.validate_battery_config(config)
        v2=[x for x in config["jobs"] if x["prompt_version"]=="v2"]; v1=[x for x in config["jobs"] if x["prompt_version"]=="v1"]
        self.assertEqual((len({x["family"] for x in v2}),len(v1)),(4,1)); self.assertIn(v1[0]["model"],{x["model"] for x in v2}); self.assertGreaterEqual(len({x["price_tier"] for x in config["jobs"]}),2)
if __name__=="__main__": unittest.main()

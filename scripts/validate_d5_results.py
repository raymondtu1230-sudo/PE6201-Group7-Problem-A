#!/usr/bin/env python3
"""Recompute and strictly validate one D5 result directory."""
from __future__ import annotations
import argparse,json,math,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.create_d5_lock import canonical,verify_lock
from scripts.run_d5_live import load_labels,planned_runs
from src.d4_evaluation import score_trial,validate_annotations
from src.claim_agent import DECISION_RECORD_SCHEMA
from scripts.run_d5_live import tool_order,complete_provider_usage
from scripts.d5_safety import known_cost
SECRET=re.compile(r"(?i)(authorization\s*:|bearer\s+[A-Za-z0-9_-]{12,}|sk-[A-Za-z0-9_-]{12,})")
def nonnegative_number(x:object)->bool: return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>=0
def validate(directory:Path,lock_path:Path,allow_incomplete:bool=False)->dict:
    raw="\n".join(p.read_text(errors="replace") for p in directory.glob("*.*") if p.is_file())
    if SECRET.search(raw): raise ValueError("likely secret or authorization header")
    lock=json.loads(lock_path.read_text()); verified=verify_lock(lock); lock_hash=verified["lock_hash"]
    manifest=json.loads((directory/"job_manifest.json").read_text()); config=json.loads((ROOT/"config/d5_jobs.json").read_text())
    matches=[j for j in config["jobs"] if all(manifest.get(k)==j[k] for k in ("member","model","prompt_version"))]
    if len(matches)!=1 or manifest.get("generation_settings")!=config["generation_settings"]: raise ValueError("manifest does not identify one configured job")
    if manifest.get("baseline_commit")!=lock["baseline_commit"] or manifest.get("lock_hash")!=lock_hash: raise ValueError("manifest lock mismatch")
    rows=[json.loads(x) for x in (directory/"trials.jsonl").read_text().splitlines()]; completed=[x for x in rows if x.get("transport_status")=="model_response"]
    attempts=[(x.get("run_id"),x.get("attempt")) for x in rows]
    if len(attempts)!=len(set(attempts)) or any(not isinstance(x[1],int) or x[1]<1 for x in attempts): raise ValueError("duplicate or invalid attempt number")
    for row in rows:
        usage=row.get("provider_usage",[])
        if not isinstance(usage,list) or any(not isinstance(x,dict) for x in usage): raise ValueError("invalid provider usage")
        if "known_cost_usd" in row and row["known_cost_usd"]!=known_cost(usage): raise ValueError("known paid cost was not retained")
        if usage and all(all(nonnegative_number(x.get(k)) for k in ("prompt_tokens","completion_tokens","cost")) for x in usage):
            if row.get("cost_source")!="provider_measured" or row.get("cost_usd")!=sum(x["cost"] for x in usage): raise ValueError("paid-attempt cost was not retained")
    expected={x["run_id"]:x for x in planned_runs()}; ids=[x.get("run_id") for x in completed]
    for row in rows:
        if row.get("run_id") not in expected: raise ValueError("unknown run ID")
        if row.get("transport_status") not in {"model_response","transport_failure","provider_failure"}: raise ValueError("unknown transport status")
        if any(row.get(k)!=expected[row["run_id"]][k] for k in ("case_id","trial","negative")): raise ValueError("schedule row mismatch")
        if any(row.get(k)!=manifest[k] for k in ("member","model","prompt_version","generation_settings","baseline_commit","lock_hash")): raise ValueError("mixed job or lock")
    if len(ids)!=len(set(ids)): raise ValueError("duplicate completed model response")
    billing_complete=all(x.get("cost_usd") is not None and x.get("billing_complete",True) for x in rows)
    if not allow_incomplete and not billing_complete: raise ValueError("unresolved billing evidence")
    if not allow_incomplete and (len(ids)!=70 or set(ids)!=set(expected)): raise ValueError("exactly 70 scheduled model responses required")
    if any(rid not in expected for rid in ids): raise ValueError("unknown run ID")
    labels,facts=load_labels(); labelmap={x["case_id"]:x for x in labels}; claims={x["claim_id"]:x for x in facts["claims"]}
    for row in completed:
        exp=expected[row["run_id"]]
        if any(row.get(k)!=exp[k] for k in ("case_id","trial","negative")): raise ValueError("schedule row mismatch")
        if any(row.get(k)!=manifest[k] for k in ("member","model","prompt_version","generation_settings","baseline_commit","lock_hash")): raise ValueError("mixed job or lock")
        if row.get("prompt_descriptor_hash")!=lock["prompts"][manifest["prompt_version"]]: raise ValueError("prompt hash mismatch")
        if not isinstance(row.get("trace"),list) or not row["trace"]: raise ValueError("incomplete trace")
        if row.get("automatic_pass") and (not isinstance(row.get("decision_record"),dict) or any(k not in row["decision_record"] for k in DECISION_RECORD_SCHEMA["required"])): raise ValueError("passing trial has incomplete decision schema")
        if isinstance(row.get("decision_record"),dict):
            duplicate_fields=set(DECISION_RECORD_SCHEMA["duplicate_assessment_item_exact_fields"])
            if any(not isinstance(x,dict) or set(x)!=duplicate_fields for x in row["decision_record"].get("duplicate_assessment",[])): raise ValueError("noncanonical duplicate assessment")
        if row.get("tool_order")!=tool_order(row["trace"]) or not isinstance(row.get("tool_calls"),int) or row["tool_calls"]<0: raise ValueError("invalid tool evidence")
        if not isinstance(row.get("provider_usage"),list) or not isinstance(row.get("provider_responses"),list): raise ValueError("invalid provider evidence")
        scored=score_trial(labelmap[row["case_id"]],row["decision_record"],claims[row["case_id"]],facts,autonomy="confirm",confirmed=True,write_count=row.get("write_count"),halt_reason=row.get("halt_reason"))
        if row.get("automatic_pass") is not scored["passed"] or row.get("failed_checks")!=scored["failed_checks"] or row.get("checks")!=scored["checks"]: raise ValueError("stored score/checks do not match recomputation")
        if not nonnegative_number(row.get("latency_seconds")): raise ValueError("invalid latency value")
        if (allow_incomplete and row.get("halt_reason")=="paid_malformed_response"
                and (not row.get("provider_usage") or
                     any(not complete_provider_usage(item) for item in row["provider_usage"]))):
            # Audit evidence is valid even with unknown billing. inspect_live_job
            # separately blocks any further spending; final validation still fails.
            continue
        if not all(nonnegative_number(row.get(k)) for k in ("input_tokens","output_tokens")): raise ValueError("invalid token or latency value")
        usage=row["provider_usage"]
        if len(usage)!=row.get("model_calls") or any(not all(nonnegative_number(x.get(k)) for k in ("prompt_tokens","completion_tokens","cost")) for x in usage): raise ValueError("incomplete per-call provider usage")
        if row.get("token_source")!="provider_measured" or row["input_tokens"]!=sum(x["prompt_tokens"] for x in usage) or row["output_tokens"]!=sum(x["completion_tokens"] for x in usage): raise ValueError("false provider-measured token evidence")
        if row.get("cost_source") != "provider_measured" or not nonnegative_number(row.get("cost_usd")): raise ValueError("missing provider-measured cost provenance")
        if row["cost_source"]=="provider_measured" and row["cost_usd"]!=sum(x["cost"] for x in usage): raise ValueError("provider cost total mismatch")
    if not allow_incomplete:
        if len({x["case_id"] for x in completed})!=50 or sum(x["negative"] for x in completed)!=30 or len({x["case_id"] for x in completed if x["negative"]})!=10: raise ValueError("wrong case/negative counts")
    queue=json.loads((directory/"judgement_queue.json").read_text()); annotations=json.loads((directory/"human_review_annotations.json").read_text()); validate_annotations(queue,annotations)
    judged_cases={x["case_id"] for x in completed if labelmap[x["case_id"]].get("grading_method","code")=="judged"}
    if {x.get("case_id") for x in queue}!=judged_cases or len(queue)!=len(judged_cases): raise ValueError("judgement queue is not one-per-judged-case")
    if any(not isinstance(x.get("must_record"),list) or
           not (x.get("candidate_reason") is None or isinstance(x.get("candidate_reason"),str)) or
           not isinstance(x.get("candidate_record_reference"),str) or not x.get("run_id") or
           x.get("review_criterion") is None for x in queue): raise ValueError("incomplete judgement queue evidence")
    for item in queue:
        candidates=[row for row in completed if row["case_id"]==item["case_id"]]
        candidate=candidates[-1]
        record=candidate.get("decision_record") or {}
        if (item["run_id"]!=candidate["run_id"] or
                item.get("candidate_reason")!=record.get("reason") or
                item["candidate_record_reference"]!=f"trials.jsonl#run_id={candidate['run_id']}"):
            raise ValueError("judgement queue does not match retained candidate")
        # An absent candidate is a scored failure, not corrupt evaluation data.
        # It remains pending for truthful review and can never pass the code checks.
    amap={(x["run_id"],x["case_id"]):x for x in annotations}; finals=[]
    for row in completed:
        passed=row["automatic_pass"]
        if labelmap[row["case_id"]].get("grading_method","code")=="judged":
            queue_item=next(x for x in queue if x["case_id"]==row["case_id"]); status=amap[(queue_item["run_id"],row["case_id"])]["status"]
            passed=passed and status=="approved"
        finals.append((row,passed))
    summary=json.loads((directory/"summary.json").read_text())
    pending=any(x["status"]=="pending" for x in annotations)
    if summary.get("status")=="complete":
        if pending or len(completed)!=70 or not billing_complete: raise ValueError("complete result has pending/incomplete reviews or billing")
        overall=sum(x[1] for x in finals)/70; neg=[x for x in finals if x[0]["negative"]]; negative=sum(x[1] for x in neg)/30
        if summary.get("final_pass_rate")!=overall or summary.get("negative_pass_rate")!=negative: raise ValueError("final rates do not match recomputation")
    paid_attempt_cost=sum(known_cost(x.get("provider_usage",[])) for x in rows)
    return {"valid":True,"complete":summary.get("status")=="complete","model":manifest["model"],"member":manifest["member"],"prompt_version":manifest["prompt_version"],"trials":len(completed),"finals":finals,"paid_attempt_cost_usd":paid_attempt_cost,
            "billing_complete":billing_complete}
def main()->None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("directory",type=Path); p.add_argument("--lock",type=Path,required=True); p.add_argument("--allow-incomplete",action="store_true"); a=p.parse_args(); result=validate(a.directory,a.lock,a.allow_incomplete); result.pop("finals"); print(json.dumps(result,indent=2))
if __name__=="__main__": main()

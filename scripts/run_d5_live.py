#!/usr/bin/env python3
"""Staged, sequential and resumable D5 runner; default mode is network-free."""
from __future__ import annotations
import argparse,json,os,sys,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from src.claim_agent import ClaimAgent, assert_decision_contract, normalize_action
from src.live_backend import assert_live_message_contract
from src.d4_evaluation import build_schedule,load_facts,score_trial,validate_annotations,validate_answer_key
from scripts.create_d5_lock import canonical,verify_lock
D5_MAX_STEPS=8  # Scripted parallel evidence peaks at 6 calls; two turns are a controlled margin.
MAX_NEW_RUNS_BOUND=70

def validate_battery_config(config:dict)->None:
    jobs=config.get("jobs",[]); v2=[x for x in jobs if x.get("prompt_version")=="v2"]; v1=[x for x in jobs if x.get("prompt_version")=="v1"]
    if len(jobs)!=5 or len(v2)!=4 or len(v1)!=1 or len({x.get("family") for x in v2})!=4:
        raise ValueError("battery must contain four unique v2 families and exactly one v1 job")
    if len({x.get("price_tier") for x in jobs})<2 or v1[0].get("model") not in {x.get("model") for x in v2}:
        raise ValueError("battery requires two planned price tiers and a fixed-model v1/v2 pair")
    if not all(x.get("prompt_version")=="v2" for x in v2) or not isinstance(config.get("generation_settings"),dict):
        raise ValueError("v2 jobs must share one generation-settings block and v2 descriptor")
    required={"member","model","prompt_version","family","price_tier"}
    if any(not required.issubset(job) or not all(isinstance(job[k],str) and job[k] for k in required)
           for job in jobs): raise ValueError("every job requires nonblank identity fields")
    if (not isinstance(config.get("run_budget_usd"),(int,float)) or config["run_budget_usd"]<=0 or
            not isinstance(config.get("job_budget_usd"),(int,float)) or
            config["job_budget_usd"] < config["run_budget_usd"]):
        raise ValueError("invalid D5 budget caps")

def preflight_live_job(*,job_number:int,output:Path,lock_path:Path,max_new_runs:int)->tuple[dict,dict,dict,list[dict]]:
    """Perform every local compatibility check before an agent/provider exists."""
    if not isinstance(job_number,int) or not 1<=job_number<=5:
        raise ValueError("job_number must be between 1 and 5")
    if not 1<=max_new_runs<=MAX_NEW_RUNS_BOUND:
        raise ValueError("max_new_runs must be between 1 and 70")
    config=json.loads((ROOT/"config/d5_jobs.json").read_text()); validate_battery_config(config)
    job=config["jobs"][job_number-1]
    if job["prompt_version"] not in ("v1","v2"):
        raise ValueError("configured prompt version is unavailable")
    # This exercises the declared fields, enums, mappings, canonical example,
    # normalizer and structural validator rather than searching prompt strings.
    assert_decision_contract()
    # This is a zero-network quota guard: every paid run must replay the prior
    # assistant Action and completed Observation as an actual chat sequence.
    assert_live_message_contract()
    lock=json.loads(lock_path.read_text()); verified=verify_lock(lock)
    schedule=planned_runs()
    if len(schedule)!=MAX_NEW_RUNS_BOUND or len({x["run_id"] for x in schedule})!=len(schedule):
        raise ValueError("D5 schedule is incompatible with run caps")
    if output.exists() and not output.is_dir():
        raise ValueError("output path is not a directory")
    rows=[]
    result_path=output/"trials.jsonl"
    if result_path.exists():
        rows=[json.loads(x) for x in result_path.read_text().splitlines()]
        attempts=[(x.get("run_id"),x.get("attempt")) for x in rows]
        if len(attempts)!=len(set(attempts)):
            raise ValueError("duplicate existing run attempt")
        if any(x.get("run_id") not in {r["run_id"] for r in schedule} for x in rows):
            raise ValueError("incompatible output contains an unknown run ID")
    return config,job,{"lock":lock,"verified":verified},rows
def atomic_json(path:Path,value:object)->None:
    tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n"); tmp.replace(path)
def load_labels()->tuple[list[dict],dict]:
    facts=load_facts(); return validate_answer_key(json.loads((ROOT/"expected_outcomes_A.json").read_text()),facts),facts
def planned_runs()->list[dict]:
    labels,_=load_labels()
    return [{"run_id":x["run_id"],"case_id":x["label"]["case_id"],"trial":x["trial"],
             "negative":x["metadata"]["negative"]} for x in build_schedule(labels)]
def tool_order(trace:list[dict])->list[str]:
    order=[]
    for event in trace:
        if "Action" not in event: continue
        try: calls=normalize_action(event["Action"])
        except ValueError: continue
        order.extend(x.get("tool") for x in calls if isinstance(x,dict) and isinstance(x.get("tool"),str))
    return order
def complete_provider_usage(item:dict)->bool:
    return all(isinstance(item.get(k),(int,float)) and not isinstance(item.get(k),bool) and item[k]>=0
               for k in ("prompt_tokens","completion_tokens","cost"))
def cost_evidence(usages:list[dict],model:str,pricing:dict)->tuple[float|None,str,dict|None]:
    if usages and all(complete_provider_usage(x) for x in usages):
        costs=[x["cost"] for x in usages]
        return sum(costs),"provider_measured",{"per_call":costs}
    price=(pricing.get("models") or {}).get(model)
    tokens_complete=usages and all(all(isinstance(x.get(k),int) and not isinstance(x.get(k),bool) and x[k]>=0
                                      for k in ("prompt_tokens","completion_tokens")) for x in usages)
    dated_source = isinstance(pricing.get("source"), str) and pricing["source"].strip() and isinstance(pricing.get("effective_date"), str) and pricing["effective_date"].strip()
    if tokens_complete and dated_source and price and all(isinstance(price.get(k),(int,float)) and price[k]>=0 for k in ("input_per_million","output_per_million")):
        inp=sum(int(x.get("prompt_tokens",0)) for x in usages); out=sum(int(x.get("completion_tokens",0)) for x in usages)
        return (inp*price["input_per_million"]+out*price["output_per_million"])/1_000_000,"locally_calculated",{"source":pricing.get("source"),"effective_date":pricing.get("effective_date"),"rates":price}
    return None,"unavailable",None
def job_manifest(job:dict,settings:dict,lock:dict,lock_hash:str)->dict:
    return {**job,"generation_settings":settings,"baseline_commit":lock["baseline_commit"],"lock_hash":lock_hash,
            "planned_case_count":50,"planned_trial_count":70,"started_at":datetime.now(timezone.utc).isoformat()}
def ensure_manifest(output:Path,expected:dict,*,create:bool=True)->dict:
    path=output/"job_manifest.json"
    if path.exists():
        got=json.loads(path.read_text()); identity=("member","model","prompt_version","generation_settings","baseline_commit","lock_hash","planned_case_count","planned_trial_count")
        if any(got.get(k)!=expected.get(k) for k in identity): raise ValueError("output directory job manifest mismatch")
        return got
    if create: atomic_json(path,expected)
    return expected

def inspect_live_job(*,job_number:int,output:Path,lock_path:Path,max_new_runs:int)->dict:
    """The actual keyless, read-only preflight, shared with paid execution checks."""
    config,job,info,rows=preflight_live_job(job_number=job_number,output=output,
        lock_path=lock_path,max_new_runs=max_new_runs)
    ensure_manifest(output,job_manifest(job,config["generation_settings"],info["lock"],
        info["verified"]["lock_hash"]),create=False)
    if not rows and max_new_runs!=1:
        raise ValueError("an empty output directory requires the mandatory --max-new-runs 1 smoke test")
    if rows:
        from scripts.validate_d5_results import validate
        validate(output,lock_path,allow_incomplete=True)
    attempted={row["run_id"] for row in rows}
    remaining=[item for item in planned_runs() if item["run_id"] not in attempted]
    return {"mode":"preflight","valid":True,"network_requests":0,**info["verified"],
        **job,"output":str(output),"existing_attempts":len(rows),
        "remaining_unattempted_trials":len(remaining),"max_new_runs":max_new_runs,
        "next_run_id":remaining[0]["run_id"] if remaining else None,
        "live_max_steps":D5_MAX_STEPS}
def rebuild_reviews(output:Path,rows:list[dict],labels:dict[str,dict])->None:
    judged={x["case_id"]:x for x in rows if x.get("transport_status")=="model_response" and labels[x["case_id"]].get("grading_method","code")=="judged"}
    queue=[{"run_id":r["run_id"],"case_id":cid,"review_criterion":labels[cid].get("note"),"must_record":labels[cid]["must_record"],
            "candidate_reason":(r.get("decision_record") or {}).get("reason"),"candidate_record_reference":f"trials.jsonl#run_id={r['run_id']}"} for cid,r in sorted(judged.items())]
    ap=output/"human_review_annotations.json"; old=json.loads(ap.read_text()) if ap.exists() else []
    oldmap={(x.get("run_id"),x.get("case_id")):x for x in old}
    annotations=[oldmap.get((x["run_id"],x["case_id"]),{"run_id":x["run_id"],"case_id":x["case_id"],"status":"pending","reviewer":"","review_note":""}) for x in queue]
    validate_annotations(queue,annotations); atomic_json(output/"judgement_queue.json",queue); atomic_json(ap,annotations)
def write_summary(output:Path,rows:list[dict],labels:dict[str,dict],status_hint:str="incomplete")->None:
    completed=[x for x in rows if x.get("transport_status")=="model_response"]
    annotations=json.loads((output/"human_review_annotations.json").read_text())
    amap={x["case_id"]:x["status"] for x in annotations}
    final=[]
    for row in completed:
        passed=row["automatic_pass"]
        if labels[row["case_id"]].get("grading_method","code")=="judged": passed=passed and amap.get(row["case_id"])=="approved"
        final.append((row,passed))
    pending=any(x["status"]=="pending" for x in annotations); cost_missing=any(x.get("cost_usd") is None for x in completed)
    complete=len(completed)==70 and not pending and not cost_missing
    negatives=[x for x in final if x[0]["negative"]]
    atomic_json(output/"summary.json",{"status":"complete" if complete else status_hint,
        "completed_model_responses":len(completed),"final_pass_rate":sum(x[1] for x in final)/70 if complete else None,
        "negative_pass_rate":sum(x[1] for x in negatives)/30 if complete else None,
        "judgements_pending":pending,"cost_evidence_missing":cost_missing})
def run_live_job(*,job_number:int,output:Path,lock_path:Path,max_new_runs:int,
                 retry_run_id:str|None=None,agent_factory=ClaimAgent)->int:
    config,job,lock_info,rows=preflight_live_job(job_number=job_number,output=output,
        lock_path=lock_path,max_new_runs=max_new_runs)
    lock,verified=lock_info["lock"],lock_info["verified"]; settings=config["generation_settings"]
    output.mkdir(parents=True,exist_ok=True)
    manifest=ensure_manifest(output,job_manifest(job,settings,lock,verified["lock_hash"]))
    result_path=output/"trials.jsonl"
    if not rows and max_new_runs != 1:
        raise ValueError("an empty output directory requires the mandatory --max-new-runs 1 smoke test")
    completed=[x for x in rows if x.get("transport_status")=="model_response"]
    completed_ids=[x["run_id"] for x in completed]
    if len(completed_ids)!=len(set(completed_ids)): raise ValueError("duplicate completed model-response row")
    attempted_ids={x["run_id"] for x in rows}
    labels,facts=load_labels(); labelmap={x["case_id"]:x for x in labels}; claims={x["claim_id"]:x for x in facts["claims"]}
    schedule=planned_runs()
    if retry_run_id is not None:
        if max_new_runs != 1: raise ValueError("--retry-run-id requires --max-new-runs 1 and may incur another charge")
        prior=[x for x in rows if x.get("run_id")==retry_run_id]
        if not prior or retry_run_id not in {x["run_id"] for x in schedule}: raise ValueError("retry run ID is not a previously attempted scheduled run")
        if any(x.get("transport_status")=="model_response" for x in prior): raise ValueError("a completed provider response cannot be retried")
        schedule=[next(x for x in schedule if x["run_id"]==retry_run_id)]
    count=0
    for item in schedule:
        if retry_run_id is None and item["run_id"] in attempted_ids: continue
        if count>=max_new_runs: break
        spent=sum(x["cost_usd"] for x in rows if isinstance(x.get("cost_usd"),(int,float)))
        if spent + config["run_budget_usd"] > config["job_budget_usd"]:
            rebuild_reviews(output,rows,labelmap); write_summary(output,rows,labelmap,"job_budget_cap"); return 4
        with tempfile.TemporaryDirectory(prefix="d5-") as tmp:
            started=time.monotonic(); agent=agent_factory(log_path=Path(tmp)/"decision.jsonl",backend="live",model=job["model"],descriptor_version=job["prompt_version"],execution_mode="parallel",max_steps=D5_MAX_STEPS,budget_usd=config["run_budget_usd"],generation_settings=settings)
            result=agent.run(item["case_id"],autonomy="confirm",confirm=True); elapsed=time.monotonic()-started
        record=result.decision_record; score=score_trial(labelmap[item["case_id"]],record,claims[item["case_id"]],facts,autonomy="confirm",confirmed=True,write_count=result.write_count,halt_reason=result.halt_reason)
        cost,cost_source,cost_detail=cost_evidence(result.provider_usage,job["model"],config.get("pricing",{}))
        usage_complete=bool(result.provider_usage) and all(complete_provider_usage(x) for x in result.provider_usage)
        provider_in=sum(int(x["prompt_tokens"]) for x in result.provider_usage) if usage_complete else None
        provider_out=sum(int(x["completion_tokens"]) for x in result.provider_usage) if usage_complete else None
        transport_failure=result.halt_reason in {"transport_error", "authentication_error"}
        attempt=1+max((x.get("attempt",1) for x in rows if x.get("run_id")==item["run_id"]),default=0)
        row={**item,**job,"attempt":attempt, "generation_settings":settings,"baseline_commit":lock["baseline_commit"],"lock_hash":verified["lock_hash"],"prompt_descriptor_hash":lock["prompts"][job["prompt_version"]],"run_date":manifest["started_at"],
             "decision_record":record,"trace":result.trace,"halt_reason":result.halt_reason,"write_count":result.write_count,"gate_result":record.get("gate_result") if record else None,"tool_order":tool_order(result.trace),"tool_calls":result.tool_calls,
             "code_result":"passed" if score["passed"] else "failed","automatic_pass":score["passed"],"failed_checks":score["failed_checks"],"checks":score["checks"],"provider_usage":result.provider_usage,"provider_responses":result.provider_responses,
             "model_calls":result.model_calls,"action_turns":result.action_turns,
             "input_tokens":provider_in,"output_tokens":provider_out,"token_source":"provider_measured" if usage_complete else "unavailable","latency_seconds":elapsed,"cost_usd":cost,"cost_source":cost_source,"cost_detail":cost_detail,
             "transport_status":"transport_failure" if transport_failure else "model_response"}
        with result_path.open("a") as out: out.write(json.dumps(row,sort_keys=True)+"\n"); out.flush(); os.fsync(out.fileno())
        rows.append(row); rebuild_reviews(output,rows,labelmap); count+=1
        if transport_failure: write_summary(output,rows,labelmap,"transport_failure"); return 2
        if result.halt_reason == "paid_malformed_response": write_summary(output,rows,labelmap,"paid_malformed_response"); return 3
        if result.halt_reason == "budget_cap": write_summary(output,rows,labelmap,"run_budget_cap"); return 4
    rebuild_reviews(output,rows,labelmap); write_summary(output,rows,labelmap)
    return 0
def main()->None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--job",type=int,choices=range(1,6)); p.add_argument("--output",type=Path); p.add_argument("--backend",default="scripted",choices=("scripted","live")); p.add_argument("--confirm-live",action="store_true"); p.add_argument("--baseline-lock",type=Path); p.add_argument("--max-new-runs",type=int); p.add_argument("--retry-run-id")
    p.add_argument("--preflight",action="store_true",help="validate a job, lock and output without a key, network or writes")
    a=p.parse_args()
    if a.preflight:
        if None in (a.job,a.output,a.baseline_lock):
            raise SystemExit("preflight requires --job, --output and --baseline-lock")
        try:
            print(json.dumps(inspect_live_job(job_number=a.job,output=a.output,
                lock_path=a.baseline_lock,max_new_runs=1 if a.max_new_runs is None else a.max_new_runs),indent=2))
        except (ValueError,OSError,json.JSONDecodeError) as exc:
            raise SystemExit(f"preflight refused: {exc}")
        return
    if a.backend!="live": print(json.dumps({"mode":"dry-run","network_requests":0,"cases":50,"trials_per_job":70,"jobs":5,"live_max_steps":D5_MAX_STEPS},indent=2)); return
    if not a.confirm_live or not os.environ.get("OPENROUTER_API_KEY"): raise SystemExit("live execution refused: explicit confirmation and OPENROUTER_API_KEY are required")
    if None in (a.job,a.output,a.baseline_lock,a.max_new_runs): raise SystemExit("live execution requires --job, --output, --baseline-lock, and --max-new-runs")
    try: code=run_live_job(job_number=a.job,output=a.output,lock_path=a.baseline_lock,max_new_runs=a.max_new_runs,retry_run_id=a.retry_run_id)
    except (ValueError,OSError,json.JSONDecodeError) as exc: raise SystemExit(f"live execution refused: {exc}")
    raise SystemExit(code)
if __name__=="__main__": main()

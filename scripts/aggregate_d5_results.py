#!/usr/bin/env python3
"""Aggregate complete, independently validated D5 results without version pooling."""
from __future__ import annotations
import argparse,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from scripts.validate_d5_results import validate
def metrics(info:dict)->dict:
    finals=info["finals"]; rows=[x[0] for x in finals]; neg=[x for x in finals if x[0]["negative"]]
    turns=[x["model_calls"] for x in rows]; tools=[x["tool_calls"] for x in rows]
    mean=lambda key,xs:sum(float(x[0].get(key) or 0) for x in xs)/len(xs)
    return {"trials":len(rows),"overall_pass_rate":sum(x[1] for x in finals)/len(rows),"negative_trials":len(neg),"negative_pass_rate":sum(x[1] for x in neg)/len(neg),
            "mean_turns":sum(turns)/len(turns),"median_turns":statistics.median(turns),"worst_case_turns":max(turns),"step_cap_runs":sum(x["halt_reason"]=="step_cap" for x in rows),
            "mean_tool_calls":sum(tools)/len(tools),"total_tool_calls":sum(tools),"input_tokens":sum(x["input_tokens"] for x in rows),"output_tokens":sum(x["output_tokens"] for x in rows),"mean_latency_seconds":mean("latency_seconds",finals),"cost_usd_all_paid_attempts":info["paid_attempt_cost_usd"]}
def aggregate(directories:list[Path],lock:Path)->dict:
    groups={"v2_cross_model":{},"gemini_v1_v2":{}}; seen=set(); infos=[]
    for d in directories:
        info=validate(d,lock)
        if not info["complete"]: raise ValueError("aggregation requires complete results")
        key=(info["model"],info["prompt_version"])
        if key in seen: raise ValueError("duplicate model/version result directory")
        seen.add(key); infos.append(info)
    for info in infos:
        key=(info["model"],info["prompt_version"])
        target="v2_cross_model" if info["prompt_version"]=="v2" else "gemini_v1_v2"; groups[target][f'{key[0]}:{key[1]}']=metrics(info)
    gemini="google/gemini-2.5-flash-lite:v2"
    if gemini in groups["v2_cross_model"]: groups["gemini_v1_v2"][gemini]=groups["v2_cross_model"][gemini]
    return groups
def main()->None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("directories",nargs="+",type=Path); p.add_argument("--lock",required=True,type=Path); a=p.parse_args(); print(json.dumps(aggregate(a.directories,a.lock),indent=2))
if __name__=="__main__": main()

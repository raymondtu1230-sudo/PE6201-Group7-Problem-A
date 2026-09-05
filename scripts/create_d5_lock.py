#!/usr/bin/env python3
"""Generate and verify a non-self-referential, post-merge D5 baseline lock."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from src.claim_agent import DECISION_RECORD_SCHEMA, SYSTEM_INSTRUCTION, TOOL_DESCRIPTOR_SETS
from src.d4_evaluation import build_schedule, load_facts, validate_answer_key

def sha_bytes(value: bytes)->str: return hashlib.sha256(value).hexdigest()
def sha_file(path: Path)->str: return sha_bytes(path.read_bytes())
def canonical(value: object)->str: return sha_bytes(json.dumps(value,sort_keys=True,separators=(",",":")).encode())
def locked_paths(root: Path=ROOT)->list[Path]:
    return [*sorted((root/"data_A").glob("*.json")),root/"make_fixtures_A.py",root/"expected_outcomes_A.json",
            root/"src/claim_agent.py",root/"src/live_backend.py",root/"src/d4_evaluation.py",
            root/"scripts/run_d5_live.py",root/"scripts/d5_safety.py",root/"scripts/validate_d5_results.py",
            root/"scripts/aggregate_d5_results.py",root/"scripts/create_d5_lock.py",
            root/"config/d5_jobs.json"]
def git(*args:str,root:Path=ROOT,check:bool=True)->str:
    return subprocess.run(["git",*args],cwd=root,text=True,capture_output=True,check=check).stdout.strip()
def prompt_hashes()->dict[str,str]:
    return {v:canonical({"system":SYSTEM_INSTRUCTION,"decision_schema":DECISION_RECORD_SCHEMA,
                         "tools":d,"descriptor_version":v}) for v,d in TOOL_DESCRIPTOR_SETS.items()}
def generate_lock(root:Path=ROOT,baseline_commit:str|None=None)->dict:
    baseline=baseline_commit or git("rev-parse","HEAD",root=root)
    paths=locked_paths(root); rel=[str(x.relative_to(root)) for x in paths]
    dirty=git("status","--porcelain","--",*rel,root=root)
    if dirty: raise ValueError("locked evaluation files have dirty or untracked changes")
    labels=validate_answer_key(json.loads((root/"expected_outcomes_A.json").read_text()),load_facts())
    return {"format_version":2,"baseline_commit":baseline,"files":{r:sha_file(root/r) for r in rel},
            "prompts":prompt_hashes(),"schedule":canonical(build_schedule(labels))}
def verify_lock(lock:dict,root:Path=ROOT,head_commit:str|None=None)->dict:
    head=head_commit or git("rev-parse","HEAD",root=root)
    if subprocess.run(["git","merge-base","--is-ancestor",lock["baseline_commit"],head],cwd=root).returncode:
        raise ValueError("current commit is not the locked baseline or its descendant")
    expected=set(str(x.relative_to(root)) for x in locked_paths(root))
    if set(lock.get("files",{}))!=expected: raise ValueError("locked file set is incomplete or unexpected")
    drift=[name for name,digest in lock["files"].items() if not (root/name).is_file() or sha_file(root/name)!=digest]
    if drift: raise ValueError("locked file drift: "+", ".join(drift))
    labels=validate_answer_key(json.loads((root/"expected_outcomes_A.json").read_text()),load_facts())
    if lock.get("prompts")!=prompt_hashes() or lock.get("schedule")!=canonical(build_schedule(labels)):
        raise ValueError("prompt/descriptor or schedule drift")
    return {"valid":True,"baseline_commit":lock["baseline_commit"],"head_commit":head,
            "lock_hash":canonical(lock)}
def main()->None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--output",type=Path); p.add_argument("--verify",type=Path)
    a=p.parse_args()
    if bool(a.output)==bool(a.verify): p.error("choose exactly one of --output or --verify")
    if a.verify: print(json.dumps(verify_lock(json.loads(a.verify.read_text())),indent=2)); return
    a.output.write_text(json.dumps(generate_lock(),indent=2)+"\n")
if __name__=="__main__": main()

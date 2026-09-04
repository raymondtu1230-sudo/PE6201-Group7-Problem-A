#!/usr/bin/env python3
"""Reproducible offline D2 measurements; no provider or live-system access."""
import hashlib,json,math,tempfile
from pathlib import Path
from src.claim_agent import ClaimAgent
from src.d4_evaluation import build_schedule,load_facts,score_trial,validate_answer_key
from scripts.run_guardrail_checklist import run_checklist
ROOT=Path(__file__).resolve().parents[1]
expected=validate_answer_key(json.loads((ROOT/'expected_outcomes_A.json').read_text()),load_facts())
def trials():
    for scheduled in build_schedule(expected): yield scheduled['label'],scheduled['trial']
def measure(mode,version,full_scorer=False):
    runs=[]; facts=load_facts(); claims={x['claim_id']:x for x in facts['claims']}
    with tempfile.TemporaryDirectory() as tmp:
        for label,repetition in trials():
            agent=ClaimAgent(log_path=Path(tmp)/f'{version}-{label["case_id"]}-{repetition}.jsonl',execution_mode=mode,descriptor_version=version,max_model_calls=20)
            result=agent.run(label['case_id'],confirm=True); record=result.decision_record or {}
            scored=score_trial(label,record,claims[label['case_id']],facts,autonomy='confirm',confirmed=True,write_count=result.write_count,halt_reason=result.halt_reason)
            passed=scored['passed'] if full_scorer else record.get('decision')==label['expected_decision']
            runs.append({'case_id':label['case_id'],'repetition':repetition,'decision':record.get('decision'),'expected_decision':label['expected_decision'],'passed':passed,
              'failed_checks':scored['failed_checks'] if full_scorer else [],'tool_order':[x['Observation']['tool'] for x in result.trace if x.get('Observation',{}).get('tool')],
              'turns':result.model_calls,'action_turns':result.action_turns,'input_tokens_approx':result.input_tokens,'output_tokens_approx':result.output_tokens,
              'estimated_cost_usd':result.estimated_cost,'halt_reason':result.halt_reason,'gate_result':record.get('gate_result'),'write_count':result.write_count})
    return {'measurement':'scripted_offline_full_scorer' if full_scorer else 'scripted_offline_approximate','execution_mode':mode,'descriptor_version':version,'model':'local-rule-planner','run_count':len(runs),
      'summary':{'turns':sum(x['turns'] for x in runs),'input_tokens_approx':sum(x['input_tokens_approx'] for x in runs),'output_tokens_approx':sum(x['output_tokens_approx'] for x in runs),
       'estimated_cost_usd':sum(x['estimated_cost_usd'] for x in runs),'passed':sum(x['passed'] for x in runs),'pass_rate':sum(x['passed'] for x in runs)/len(runs)},'runs':runs}
def profile(version):
    agent=ClaimAgent(descriptor_version=version); payloads=[json.dumps(agent.get_claim(x['case_id']),sort_keys=True,separators=(',',':')) for x in expected]
    chars=[len(x) for x in payloads]; tokens=[math.ceil(len(x.encode('utf-8'))/4) for x in payloads]
    return {'tool':'get_claim','descriptor_version':version,'cases':len(chars),'min_chars':min(chars),'max_chars':max(chars),'mean_chars':round(sum(chars)/len(chars),2),'total_chars':sum(chars),
            'token_method':'ceil(UTF-8 serialized JSON bytes / 4)','tokenizer':'deterministic byte-ratio estimator','exact':False,'min_tokens_approx':min(tokens),'mean_tokens_approx':round(sum(tokens)/len(tokens),2),'max_tokens_approx':max(tokens),'total_tokens_approx':sum(tokens)}
out=ROOT/'results/d2'; out.mkdir(parents=True,exist_ok=True)
for mode in ('sequential','parallel'): (out/f'scripted_{mode}.json').write_text(json.dumps(measure(mode,'v2'),indent=2,sort_keys=True)+'\n')
full={'measurement':'full D4 score_trial over fixed 70-trial schedule','live_results':'pending','versions':{v:measure('parallel',v,True) for v in ('v1','v2')}}
(out/'versioned_full_scorer.json').write_text(json.dumps(full,indent=2,sort_keys=True)+'\n')
guards={v:run_checklist(v) for v in ('v1','v2')}; guard_payload={'measurement':'D2 descriptor-version guardrail comparison','live_results':'pending','versions':{v:{'passed':sum(x['passed'] for x in rows),'total':len(rows),'cases':rows} for v,rows in guards.items()}}
(out/'descriptor_guardrails.json').write_text(json.dumps(guard_payload,indent=2,sort_keys=True)+'\n')
profiles={'measurement':'serialized compact JSON characters and deterministic approximate tokens over all 50 claims','provider_tokens':'pending until controlled D5','profiles':[profile('v1'),profile('v2')]}
(out/'observation_profile.json').write_text(json.dumps(profiles,indent=2,sort_keys=True)+'\n')
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('*.json')) if p.name!='manifest.json'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
print(json.dumps({'profiles':profiles['profiles'],'full_scorer':{v:x['summary'] for v,x in full['versions'].items()},'guardrails':{v:{k:d[k] for k in ('passed','total')} for v,d in guard_payload['versions'].items()},'sequential':json.loads((out/'scripted_sequential.json').read_text())['summary'],'parallel':json.loads((out/'scripted_parallel.json').read_text())['summary']},indent=2))

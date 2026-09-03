#!/usr/bin/env python3
"""Reproducible offline D2 measurements; no provider or live-system access."""
import hashlib, json, tempfile
from pathlib import Path
from src.claim_agent import ClaimAgent
ROOT=Path(__file__).resolve().parents[1]
expected=json.loads((ROOT/'expected_outcomes_A.json').read_text())

def trials():
    for row in expected:
        for repetition in range(3 if row['expected_decision'] != 'approve_in_principle' else 1):
            yield row, repetition+1

def measure(mode, version):
    runs=[]
    with tempfile.TemporaryDirectory() as tmp:
        agent=ClaimAgent(log_path=Path(tmp)/'decisions.jsonl', execution_mode=mode,
                         descriptor_version=version, max_model_calls=20)
        for label, repetition in trials():
            result=agent.run(label['case_id'], confirm=True)
            record=result.decision_record or {}
            gate_observations=[x['Observation']['result'].get('gate_result') for x in result.trace
              if x.get('Observation',{}).get('tool') == 'issue_decision_letter']
            runs.append({'case_id':label['case_id'],'repetition':repetition,
              'decision':record.get('decision'),'expected_decision':label['expected_decision'],
              'passed':record.get('decision')==label['expected_decision'],
              'tool_order':[x['Observation']['tool'] for x in result.trace if x.get('Observation',{}).get('tool')],
              'turns':result.model_calls,'action_turns':result.action_turns,
              'input_tokens_approx':result.input_tokens,'output_tokens_approx':result.output_tokens,
              'estimated_cost_usd':result.estimated_cost,'halt_reason':result.halt_reason,
              'gate_result':gate_observations[-1] if gate_observations else None,
              'write_count':result.write_count})
    return {'measurement':'scripted_offline_approximate','execution_mode':mode,
      'descriptor_version':version,'model':'local-rule-planner','run_count':len(runs),
      'summary':{'turns':sum(x['turns'] for x in runs),'input_tokens_approx':sum(x['input_tokens_approx'] for x in runs),
       'output_tokens_approx':sum(x['output_tokens_approx'] for x in runs),
       'estimated_cost_usd':sum(x['estimated_cost_usd'] for x in runs),
       'passed':sum(x['passed'] for x in runs),'pass_rate':sum(x['passed'] for x in runs)/len(runs)},'runs':runs}

def profile(version):
    agent=ClaimAgent(descriptor_version=version)
    sizes=[len(json.dumps(agent.get_claim(x['case_id']),sort_keys=True)) for x in expected]
    return {'tool':'get_claim','descriptor_version':version,'cases':len(sizes),'min_chars':min(sizes),
            'max_chars':max(sizes),'mean_chars':round(sum(sizes)/len(sizes),2),'total_chars':sum(sizes)}

out=ROOT/'results/d2'; out.mkdir(parents=True,exist_ok=True)
for mode in ('sequential','parallel'):
    data=measure(mode,'v2')
    (out/f'scripted_{mode}.json').write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
profiles={'measurement':'serialized JSON characters over all 50 claims','profiles':[profile('v1'),profile('v2')]}
(out/'observation_profile.json').write_text(json.dumps(profiles,indent=2,sort_keys=True)+'\n')
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('*.json')) if p.name!='manifest.json'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
print(json.dumps({'profiles':profiles['profiles'],'sequential':json.loads((out/'scripted_sequential.json').read_text())['summary'],'parallel':json.loads((out/'scripted_parallel.json').read_text())['summary']},indent=2))

import json, tempfile, unittest
from pathlib import Path
from src.claim_agent import ClaimAgent, TOOL_DESCRIPTORS, MAX_TOOL_RESULT_CHARS, _State

ROOT=Path(__file__).parents[1]
class D2ToolLayerTests(unittest.TestCase):
 def test_six_field_descriptors_complete_and_bounded(self):
  self.assertEqual({'get_claim','lookup_policy','check_coverage','get_preauthorisation','get_hospital_status','issue_decision_letter'},set(TOOL_DESCRIPTORS))
  for name,d in TOOL_DESCRIPTORS.items():
   self.assertEqual({'signature','what','input','returns','fails_when','irreversible'},set(d),name)
   self.assertTrue(all(isinstance(x,str) and x.strip() for x in d.values()))
   self.assertIn('8000',d['returns'])
 def test_bad_inputs_are_structured(self):
  a=ClaimAgent()
  self.assertEqual('invalid_input',a.get_claim(7)['error'])
  self.assertEqual('invalid_input',a.lookup_policy('wrong')['error'])
  self.assertEqual('invalid_input',a.check_coverage('47120','not-a-list','POL-3310')['error'])
  self.assertEqual('invalid_input',a.get_preauthorisation('M-2214','62480','09/02/2026')['error'])
  self.assertEqual('invalid_input',a.get_hospital_status('wrong')['error'])
  for call in (a.get_claim('CLM-8842'),a.lookup_policy('M-2214'),a.check_coverage('47120',[],'POL-3310')):
   self.assertLessEqual(len(json.dumps(a._bound_tool_result(call),sort_keys=True)),MAX_TOOL_RESULT_CHARS)
 def test_poka_yoke_unambiguous_policy_and_completion_gate(self):
  a=ClaimAgent()
  with self.assertRaises(TypeError): a.check_coverage('47120',[],member_id='M-2214')
  with tempfile.TemporaryDirectory() as tmp:
   a=ClaimAgent(log_path=Path(tmp)/'x')
   s=_State('CLM-8842','confirm',True)
   r=a.issue_decision_letter('CLM-8842',{'decision':'approve_in_principle'},state=s)
   self.assertEqual('blocked_incomplete_decision',r['gate_result']); self.assertEqual(0,s.write_count)
 def test_execution_mode_validation(self):
  with self.assertRaises(ValueError): ClaimAgent(execution_mode='sometimes')
  with self.assertRaises(ValueError): ClaimAgent(descriptor_version='v3')
 def test_v1_v2_same_decisions_and_v2_is_smaller(self):
  labels=json.loads((ROOT/'expected_outcomes_A.json').read_text())
  with tempfile.TemporaryDirectory() as tmp:
   agents=[ClaimAgent(log_path=Path(tmp)/str(i),descriptor_version=v,max_model_calls=20) for i,v in enumerate(('v1','v2'))]
   for label in labels:
    got=[a.run(label['case_id'],confirm=True).decision_record['decision'] for a in agents]
    self.assertEqual([label['expected_decision']]*2,got)
  a1,a2=ClaimAgent(descriptor_version='v1'),ClaimAgent(descriptor_version='v2')
  self.assertLess(sum(len(json.dumps(a2.get_claim(x['case_id']))) for x in labels),sum(len(json.dumps(a1.get_claim(x['case_id']))) for x in labels))
 def test_sequential_parallel_turns_dependencies_and_single_write(self):
  with tempfile.TemporaryDirectory() as tmp:
   seq=ClaimAgent(log_path=Path(tmp)/'s',execution_mode='sequential',descriptor_version='v2',max_model_calls=20).run('CLM-8842',confirm=True)
   par=ClaimAgent(log_path=Path(tmp)/'p',execution_mode='parallel',descriptor_version='v2',max_model_calls=20).run('CLM-8842',confirm=True)
  self.assertEqual(seq.decision_record['decision'],par.decision_record['decision'])
  self.assertGreater(seq.model_calls,par.model_calls); self.assertEqual((1,1),(seq.write_count,par.write_count))
  for result in (seq,par):
   order=[x['Observation']['tool'] for x in result.trace if x.get('Observation',{}).get('tool')]
   self.assertLess(order.index('get_claim'),order.index('lookup_policy'))
   self.assertLess(max(i for i,x in enumerate(order) if x=='check_coverage'),min(i for i,x in enumerate(order) if x=='get_preauthorisation'))
   self.assertEqual('issue_decision_letter',order[-1])
  seq_actions=[json.loads(x['Action']) for x in seq.trace if 'Action' in x]
  self.assertTrue(all(not isinstance(x,list) or len(x)==1 for x in seq_actions))
 def test_committed_measurements_cover_70_trials_identically(self):
  data=[json.loads((ROOT/f'results/d2/scripted_{m}.json').read_text()) for m in ('sequential','parallel')]
  self.assertEqual([70,70],[x['run_count'] for x in data]); self.assertEqual([1.0,1.0],[x['summary']['pass_rate'] for x in data])
  self.assertEqual([x['decision'] for x in data[0]['runs']],[x['decision'] for x in data[1]['runs']])
  self.assertGreater(data[0]['summary']['turns'],data[1]['summary']['turns'])
  self.assertTrue(all(r['write_count']<=1 for x in data for r in x['runs']))
  self.assertEqual(140,sum(len(x['runs']) for x in data))
  self.assertTrue(all(r['gate_result']=='confirmed' for x in data for r in x['runs']))
 def test_write_gate_rejects_invalid_mismatched_and_incomplete_inputs(self):
  valid={'decision':'approve_in_principle','reason':'supported','evidence_trail':[]}
  cases=(
   ('bad',valid,'blocked_invalid_claim_id'),
   ('CLM-8850',valid,'blocked_claim_mismatch'),
   ('CLM-8842',{'decision':'invented','reason':'x','evidence_trail':[]},'blocked_decision_mismatch'),
   ('CLM-8842',{'decision':'approve_in_principle'},'blocked_decision_mismatch'),
  )
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'decisions.jsonl'; agent=ClaimAgent(log_path=path)
   for claim_id,record,expected in cases:
    with self.subTest(expected=expected):
     state=_State('CLM-8842','confirm',True,decision=valid)
     result=agent.issue_decision_letter(claim_id,record,decision_complete=True,state=state)
     self.assertEqual(expected,result['gate_result']); self.assertEqual(0,state.write_count)
     self.assertFalse(path.exists())
   state=_State('CLM-8842','confirm',True,decision={'decision':'invented','reason':'x','evidence_trail':[]})
   result=agent.issue_decision_letter('CLM-8842',state.decision,decision_complete=True,state=state)
   self.assertEqual('blocked_unsupported_decision',result['gate_result']); self.assertFalse(path.exists())
   state=_State('CLM-8842','confirm',True,decision={'decision':'approve_in_principle','reason':'','evidence_trail':[]})
   result=agent.issue_decision_letter('CLM-8842',state.decision,decision_complete=True,state=state)
   self.assertEqual('blocked_incomplete_decision',result['gate_result']); self.assertFalse(path.exists())
 def test_valid_confirmed_run_writes_exactly_once_and_does_not_rebuild(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'decisions.jsonl'; result=ClaimAgent(log_path=path).run('CLM-8842',confirm=True)
   self.assertEqual(1,result.write_count); self.assertEqual(1,len(path.read_text().splitlines()))
   gates=[x['Observation']['result']['gate_result'] for x in result.trace if x.get('Observation',{}).get('tool')=='issue_decision_letter']
   self.assertEqual(['confirmed'],gates)

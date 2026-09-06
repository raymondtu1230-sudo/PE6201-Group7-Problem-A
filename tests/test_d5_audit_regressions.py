"""Failure-path rehearsals through real HTTP serialization; no external requests."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.claim_agent import ClaimAgent, _State
from src.live_backend import call_live_model
from scripts import run_d5_live as runner
from scripts.validate_d5_results import validate
from test_d5_runner_contracts import current_lock


class WireReplay:
    """Read only serialized messages; inject specific model/transport failures."""
    def __init__(self, *, fail_cases=(), text=None, transport_case=None, cost=0.0):
        self.fail_cases = set(fail_cases)
        self.text = text
        self.transport_case = transport_case
        self.cost = cost
        self.requests = []

    def transport(self, request, timeout):
        body = json.loads(request.data)
        # Independent provider-contract fixture. Do not call the implementation's
        # validator here: a future serializer regression must fail this rehearsal.
        if body['model'] == 'anthropic/claude-haiku-4.5':
            if 'temperature' in body and 'top_p' in body:
                raise AssertionError('Haiku contract forbids two sampling parameters')
            if not 0 <= body.get('temperature', 1) <= 1:
                raise AssertionError('Haiku temperature outside provider range')
        messages = body['messages']
        task = json.loads(messages[1]['content'].split('\n', 1)[1])
        case = task['request']['claim_id']
        self.requests.append(case)
        if case == self.transport_case:
            raise OSError('simulated transport failure')
        state = _State(case, 'confirm', True)
        for index, message in enumerate(messages[2:]):
            if message['role'] != ('assistant' if index % 2 == 0 else 'user'):
                raise AssertionError('lost message roles')
            content = message['content']
            if message['role'] == 'assistant':
                thought = re.search(r'Thought:\s*(.*)', content)
                if thought:
                    state.trace.append({'Thought': thought.group(1)})
                if 'Action:' in content:
                    state.trace.append({'Action': content.split('Action:', 1)[1].strip()})
            else:
                if not content.startswith('Observation:'):
                    raise AssertionError('lost observation')
                value = json.loads(content.split('\n', 1)[1])
                for observation in value if isinstance(value, list) else [value]:
                    state.trace.append({'Observation': observation})
                    if 'result' in observation:
                        state.observations.setdefault(observation['tool'], []).append(observation['result'])
        if case in self.fail_cases:
            text = self.text or 'Final: unable to produce a decision record'
        elif 'issue_decision_letter' in state.observations:
            text = 'Final: completed'
        else:
            text = ClaimAgent(descriptor_version=task['descriptor_version']).call_model(state)
        payload = json.dumps({'id': f'fake-{len(self.requests)}', 'model': body['model'],
            'choices': [{'message': {'content': text}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'cost': self.cost}}).encode()
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return payload
        return Response()

    def factory(self, **kwargs):
        kwargs['live_caller'] = lambda **call: call_live_model(**call, transport=self.transport)
        return ClaimAgent(**kwargs)


class AuditRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lock = self.root / 'lock.json'
        self.lock.write_text(json.dumps(current_lock()))
        self.env = patch.dict(os.environ, {'OPENROUTER_API_KEY': 'offline-audit-key'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_batch(self, wire, count, job=1):
        return runner.run_live_job(job_number=job, output=self.root / 'out',
            lock_path=self.lock, max_new_runs=count, agent_factory=wire.factory)

    def test_plain_model_failure_is_retained_and_validates(self):
        raw = 'I cannot complete this request.'
        wire = WireReplay(fail_cases={'CLM-8842'}, text=raw)
        self.assertEqual(self.run_batch(wire, 1), 0)
        self.assertEqual(self.run_batch(wire, 4), 0)
        result = validate(self.root / 'out', self.lock, allow_incomplete=True)
        self.assertEqual(result['trials'], 5)
        row = result['finals'][0][0]
        self.assertFalse(row['automatic_pass'])
        self.assertTrue(any(event.get('ModelResponse') == raw for event in row['trace']))

    def test_judged_failure_survives_full_battery_and_final_validation(self):
        wire = WireReplay(fail_cases={'CLM-9029'})
        self.assertEqual(self.run_batch(wire, 1), 0)
        self.assertEqual(self.run_batch(wire, 69), 0)
        output = self.root / 'out'
        result = validate(output, self.lock, allow_incomplete=True)
        self.assertEqual(result['trials'], 70)
        self.assertEqual(sum(row['automatic_pass'] for row, _ in result['finals']), 69)
        # Test-only annotations, inside a temporary directory. These are not human reviews.
        annotations = json.loads((output / 'human_review_annotations.json').read_text())
        for item in annotations:
            item.update(status='rejected' if item['case_id'] == 'CLM-9029' else 'approved',
                        reviewer='SIMULATED TEST REVIEW', review_note='Synthetic test annotation only.')
        (output / 'human_review_annotations.json').write_text(json.dumps(annotations))
        before = len(wire.requests)
        self.assertEqual(self.run_batch(wire, 1), 0)
        self.assertEqual(len(wire.requests), before)
        self.assertTrue(validate(output, self.lock)['complete'])
        summary = json.loads((output / 'summary.json').read_text())
        self.assertEqual(summary['final_pass_rate'], 69 / 70)

    def test_budget_cap_stops_batch_after_retaining_failed_trial(self):
        self.assertEqual(self.run_batch(WireReplay(), 1), 0)
        wire = WireReplay(cost=0.09)
        self.assertNotEqual(self.run_batch(wire, 4), 0)
        self.assertEqual(len(wire.requests), 1)
        rows = (self.root / 'out/trials.jsonl').read_text().splitlines()
        self.assertEqual(len(rows), 2)
        self.assertEqual(json.loads(rows[-1])['halt_reason'], 'budget_cap')

    def test_preflight_cli_checks_lock_without_key_or_output_creation(self):
        output = self.root / 'preflight-output'
        args = [sys.executable, 'scripts/run_d5_live.py', '--preflight', '--job', '1',
                '--output', str(output), '--baseline-lock', str(self.lock), '--max-new-runs', '1']
        env = dict(os.environ)
        env.pop('OPENROUTER_API_KEY', None)
        valid = subprocess.run(args, text=True, capture_output=True, env=env)
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertTrue(json.loads(valid.stdout)['valid'])
        self.assertFalse(output.exists())
        lock = json.loads(self.lock.read_text())
        lock['files']['src/live_backend.py'] = 'broken'
        self.lock.write_text(json.dumps(lock))
        invalid = subprocess.run(args, text=True, capture_output=True, env=env)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn('drift', invalid.stderr)

    def test_public_contract_declares_scored_negative_vocabulary(self):
        task = ClaimAgent().model_input(_State('CLM-8842', 'confirm', True))
        schema = task['decision_record_schema']
        self.assertIn('instruction_in_member_narrative', schema.get('escalation_trigger_values', []))
        formats = schema.get('missing_item_formats', {})
        labels, _ = runner.load_labels()
        claims = {row['claim_id']: row for row in runner.load_facts()['claims']}
        for label in labels:
            if label['expected_decision'] != 'request_document':
                continue
            claim = claims[label['case_id']]
            options = {template.format(procedure_code=line['code'], date_of_service=claim['date_of_service'],
                       document=document) for template in formats.values() for line in claim['lines']
                       for document in ('itemised bill', 'discharge summary')}
            self.assertIn(label['missing'], options)

    def test_every_job_replays_all_70_trials_through_http_messages(self):
        for job in range(1, 6):
            with self.subTest(job=job), tempfile.TemporaryDirectory() as tmp:
                wire = WireReplay()
                output = Path(tmp) / 'out'
                for count in (1, 4, 65):
                    self.assertEqual(runner.run_live_job(job_number=job, output=output,
                        lock_path=self.lock, max_new_runs=count, agent_factory=wire.factory), 0)
                result = validate(output, self.lock, allow_incomplete=True)
                self.assertEqual(result['trials'], 70)
                self.assertEqual(sum(row['automatic_pass'] for row, _ in result['finals']), 70)
                self.assertEqual(len({row['run_id'] for row, _ in result['finals']}), 70)
                self.assertEqual(len(set(wire.requests)), 50)

    def test_five_case_model_and_transport_failures_at_each_later_position(self):
        scheduled = runner.planned_runs()[:5]
        for position in range(1, 5):
            for failure_kind in ('model', 'transport'):
                with self.subTest(position=position + 1, kind=failure_kind), tempfile.TemporaryDirectory() as tmp:
                    case = scheduled[position]['case_id']
                    wire = (WireReplay(fail_cases={case}, text='I cannot complete this request.')
                            if failure_kind == 'model' else WireReplay(transport_case=case))
                    output = Path(tmp) / 'out'
                    for count in (1, 4):
                        code = runner.run_live_job(job_number=1, output=output,
                            lock_path=self.lock, max_new_runs=count, agent_factory=wire.factory)
                    rows = [json.loads(line) for line in (output / 'trials.jsonl').read_text().splitlines()]
                    expected_count = 5 if failure_kind == 'model' else position + 1
                    self.assertEqual(len(rows), expected_count)
                    self.assertEqual(code, 0 if failure_kind == 'model' else 2)
                    self.assertFalse(rows[position]['automatic_pass'])
                    self.assertEqual([row['run_id'] for row in rows],
                                     [item['run_id'] for item in scheduled[:expected_count]])
                    self.assertTrue(validate(output, self.lock, allow_incomplete=True)['valid'])

    def test_flattened_history_regression_stops_before_transport(self):
        wire = WireReplay()
        def flattened(model_input):
            return [{'role': 'system', 'content': model_input['system']},
                    {'role': 'user', 'content': json.dumps(model_input)}]
        with patch('src.live_backend.build_live_messages', side_effect=flattened):
            with self.assertRaisesRegex(ValueError, 'role order'):
                self.run_batch(wire, 1)
        self.assertEqual(wire.requests, [])
        self.assertFalse((self.root / 'out').exists())

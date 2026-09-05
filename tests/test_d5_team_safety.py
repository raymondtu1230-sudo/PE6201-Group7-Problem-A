"""Team-wide paid-path regressions. Every response and key here is synthetic."""
import copy
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import run_d5_live as runner
from scripts.d5_safety import ACTIVE, exclusive_output
from scripts.validate_d5_results import validate
from scripts.aggregate_d5_results import aggregate
from test_d5_audit_regressions import WireReplay
from test_d5_runner_contracts import current_lock


class Response:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return json.dumps(self.payload).encode()


class FaultWire(WireReplay):
    def __init__(self, kind=None, position=1, call=3, cost=0.00001):
        super().__init__(cost=cost)
        self.kind, self.position, self.call = kind, position, call
        self.trial_number, self.trial_calls = 0, 0
        self.headers, self.models = [], []

    def factory(self, **kwargs):
        self.trial_number += 1
        self.trial_calls = 0
        return super().factory(**kwargs)

    def transport(self, request, timeout):
        self.trial_calls += 1
        body = json.loads(request.data)
        self.headers.append(request.get_header('Authorization'))
        self.models.append(body['model'])
        payload = json.loads(super().transport(request, timeout).read())
        choice = payload['choices'][0]
        choice['finish_reason'] = 'stop'
        if self.trial_number == self.position and self.trial_calls == self.call:
            if isinstance(self.kind, int):
                raise HTTPError(request.full_url, self.kind, 'synthetic failure', {}, None)
            if self.kind == 'interrupt': raise KeyboardInterrupt('synthetic interrupt')
            if self.kind == 'timeout': raise TimeoutError('synthetic timeout')
            if self.kind == 'bad_tool':
                choice['message']['content'] = 'Thought: read\nAction: {"tool":[],"arguments":{}}'
            if self.kind == 'model_json':
                choice['message']['content'] = 'Thought: read\nAction: {"tool":'
            if self.kind == 'provider_error':
                choice.update(finish_reason='error', error={'code': 502, 'message': 'synthetic provider failure'})
                choice['message']['content'] = 'Final: partial provider output'
            if self.kind == 'top_error':
                payload['error'] = {'code': 502, 'message': 'synthetic provider failure'}
            if self.kind == 'no_usage': payload.pop('usage')
            if self.kind == 'length':
                choice.update(finish_reason='length', native_finish_reason='MAX_TOKENS')
                choice['message']['content'] = 'Thought: read\nAction: {"tool":'
        return Response(payload)


class TeamSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lock = self.root / 'lock.json'
        self.lock.write_text(json.dumps(current_lock()))
        for item in (patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic-team-key'}),
                     patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')),
                     patch('socket.getaddrinfo', side_effect=AssertionError('network forbidden'))):
            item.start(); self.addCleanup(item.stop)

    def run_job(self, wire, count=1, job=1, output=None):
        return runner.run_live_job(job_number=job, output=output or self.root / 'out',
            lock_path=self.lock, max_new_runs=count, agent_factory=wire.factory)

    def rows(self, output=None):
        path = (output or self.root / 'out') / 'trials.jsonl'
        return [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []

    def test_all_five_jobs_staged_1_4_65_own_keys_and_aggregation(self):
        directories = []
        config = json.loads((runner.ROOT / 'config/d5_jobs.json').read_text())
        for job in range(1, 6):
            with self.subTest(job=job):
                output = self.root / f'job-{job}'
                key = f'private-synthetic-member-{job}'
                wire = FaultWire()
                with patch.dict(os.environ, {'OPENROUTER_API_KEY': key}):
                    for count in (1, 4, 65):
                        self.assertEqual(self.run_job(wire, count, job, output), 0)
                rows = self.rows(output)
                self.assertEqual((len(rows), len({r['case_id'] for r in rows}), sum(r['negative'] for r in rows)), (70, 50, 30))
                self.assertEqual({r['prompt_version'] for r in rows}, {config['jobs'][job-1]['prompt_version']})
                self.assertEqual(set(wire.models), {config['jobs'][job-1]['model']})
                self.assertEqual(set(wire.headers), {'Bearer ' + key})
                self.assertNotIn(key, '\n'.join(p.read_text() for p in output.iterdir() if p.is_file()))
                self.assertFalse((output / ACTIVE).exists())
                annotation_path = output / 'human_review_annotations.json'
                annotations = json.loads(annotation_path.read_text())
                self.assertEqual(len(annotations), 6)
                for row in annotations:
                    row.update(status='approved', reviewer='SYNTHETIC TEST ONLY',
                               review_note='Temporary test annotation; not a real human review.')
                annotation_path.write_text(json.dumps(annotations))
                before = len(wire.requests)
                self.assertEqual(self.run_job(wire, 1, job, output), 0)
                self.assertEqual(len(wire.requests), before)
                self.assertTrue(validate(output, self.lock)['complete'])
                directories.append(output)
        results = aggregate(directories, self.lock)
        self.assertEqual((len(results['v2_cross_model']), len(results['gemini_v1_v2'])), (4, 2))

    def test_late_failures_all_jobs_positions_6_35_70(self):
        # 60 independent late-trial scenarios through the actual wire serializer.
        for job in range(1, 6):
            for position in (6, 35, 70):
                for kind in ('bad_tool', 'model_json', 'provider_error', 429):
                    with self.subTest(job=job, position=position, kind=kind):
                        output = self.root / f'{job}-{position}-{kind}'
                        wire = FaultWire(kind, position, call=1)
                        for count in (1, 4, 65):
                            code = self.run_job(wire, count, job, output)
                            if code: break
                        rows = self.rows(output)
                        model_failure = kind in ('bad_tool', 'model_json')
                        self.assertEqual(code, 0 if model_failure else 2)
                        self.assertEqual(len(rows), 70 if model_failure else position)
                        self.assertFalse(rows[position-1]['automatic_pass'])
                        self.assertEqual(len({r['run_id'] for r in rows}), len(rows))
                        self.assertTrue(validate(output, self.lock, allow_incomplete=True)['valid'])

    def test_http_failures_keep_earlier_cost_and_stop(self):
        for status in (400, 401, 402, 403, 408, 429, 500, 502, 503, 'timeout'):
            with self.subTest(status=status):
                output = self.root / str(status)
                wire = FaultWire(status, cost=0.001)
                self.assertEqual(self.run_job(wire, output=output), 2)
                row = self.rows(output)[0]
                self.assertEqual((row['known_cost_usd'], row['cost_usd'], len(wire.requests)), (.002, .002, 3))
                self.assertFalse(row['billing_complete'])
                with self.assertRaisesRegex(ValueError, 'unresolved billing'):
                    self.run_job(wire, output=output)
                self.assertEqual(len(wire.requests), 3)

    def test_http_200_errors_stop_and_keep_partial_text_and_usage(self):
        for kind in ('provider_error', 'top_error'):
            with self.subTest(kind=kind):
                output = self.root / kind
                wire = FaultWire(kind, cost=.001)
                self.assertEqual(self.run_job(wire, output=output), 2)
                row = self.rows(output)[0]
                self.assertEqual((row['transport_status'], row['halt_reason'], row['cost_usd']),
                                 ('provider_failure', 'provider_error', .003))
                self.assertEqual(len(wire.requests), 3)
                self.assertTrue(row['provider_responses'][-1]['error'])
                self.assertTrue(any('ModelResponse' in x for x in row['trace']))
                self.assertTrue(validate(output, self.lock, allow_incomplete=True)['valid'])

    def test_length_metadata_is_retained_as_model_failure(self):
        wire = FaultWire('length')
        self.assertEqual(self.run_job(wire), 0)
        row = self.rows()[0]
        self.assertEqual(row['halt_reason'], 'malformed_json')
        self.assertEqual(row['provider_responses'][-1]['finish_reason'], 'length')
        self.assertEqual(row['provider_responses'][-1]['native_finish_reason'], 'MAX_TOKENS')
        self.assertEqual(self.run_job(wire), 0)

    def test_unknown_cost_retains_known_lower_bound_blocks_new_spend(self):
        wire = FaultWire('no_usage', cost=.001)
        self.assertEqual(self.run_job(wire), 3)
        row = self.rows()[0]
        self.assertIsNone(row['cost_usd'])
        self.assertEqual(row['known_cost_usd'], .002)
        audited = validate(self.root / 'out', self.lock, allow_incomplete=True)
        self.assertEqual(audited['paid_attempt_cost_usd'], .002)
        self.assertFalse(audited['billing_complete'])
        with self.assertRaisesRegex(ValueError, 'unresolved billing'):
            self.run_job(wire)
        self.assertEqual(len(wire.requests), 3)

    def test_interrupt_keeps_journal_and_blocks_automatic_replay(self):
        wire = FaultWire('interrupt', cost=.001)
        with self.assertRaises(KeyboardInterrupt): self.run_job(wire)
        journal = json.loads((self.root / 'out' / ACTIVE).read_text())
        self.assertEqual(journal['known_cost_usd'], .002)
        self.assertEqual(len(journal['calls']), 3)
        self.assertFalse(journal['billing_complete'])
        self.assertIn('Action:', journal['calls'][0]['text'])
        with self.assertRaisesRegex(ValueError, 'unresolved active_trial'):
            self.run_job(wire)
        with self.assertRaisesRegex(ValueError, 'automatic replay is forbidden'):
            runner.recover_live_job(job_number=1, output=self.root / 'out', lock_path=self.lock)
        self.assertEqual(len(wire.requests), 3)

    def test_program_error_keeps_returned_response_before_parsing(self):
        wire = FaultWire(cost=.001)
        with patch('src.claim_agent.ClaimAgent.execute_action_block', side_effect=RuntimeError('synthetic bug')):
            with self.assertRaises(RuntimeError): self.run_job(wire)
        journal = json.loads((self.root / 'out' / ACTIVE).read_text())
        self.assertEqual((journal['known_cost_usd'], journal['phase']), (.001, 'response_received'))
        self.assertTrue(journal['calls'][0]['text'])
        with self.assertRaisesRegex(ValueError, 'unresolved active_trial'): self.run_job(wire)
        self.assertEqual(len(wire.requests), 1)

    def test_completed_row_recovers_without_provider_after_summary_failure(self):
        wire = FaultWire()
        original = runner.atomic_json
        def fail_summary(path, value):
            if path.name == 'summary.json': raise OSError('synthetic disk failure')
            return original(path, value)
        with patch.object(runner, 'atomic_json', side_effect=fail_summary):
            with self.assertRaises(OSError): self.run_job(wire)
        before = len(wire.requests)
        self.assertEqual(len(self.rows()), 1)
        with self.assertRaisesRegex(ValueError, 'unresolved active_trial'): self.run_job(wire)
        result = runner.recover_live_job(job_number=1, output=self.root / 'out', lock_path=self.lock)
        self.assertEqual(result['network_requests'], 0)
        self.assertEqual(len(wire.requests), before)
        self.assertEqual(len(self.rows()), 1)
        self.assertTrue(validate(self.root / 'out', self.lock, allow_incomplete=True)['valid'])

    def test_append_failure_keeps_scored_row_and_recovers_once(self):
        wire = FaultWire(cost=.001)
        original = Path.open
        def fail_append(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get('mode', 'r')
            if path.name == 'trials.jsonl' and mode == 'a': raise OSError('synthetic ENOSPC')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', fail_append):
            with self.assertRaises(OSError): self.run_job(wire)
        checkpoint = json.loads((self.root / 'out' / ACTIVE).read_text())
        self.assertEqual(checkpoint['phase'], 'trial_scored')
        self.assertEqual(checkpoint['completed_trial']['cost_usd'], .001 * len(wire.requests))
        before = len(wire.requests)
        runner.recover_live_job(job_number=1, output=self.root / 'out', lock_path=self.lock)
        self.assertEqual((len(wire.requests), len(self.rows())), (before, 1))

    def test_existing_invalid_targets_rejected_before_provider(self):
        for name in ('summary.json', 'trials.jsonl', 'job_manifest.json', 'active_trial.json', 'summary.json.tmp'):
            with self.subTest(name=name):
                output = self.root / name
                output.mkdir(); (output / name).mkdir()
                wire = FaultWire()
                with self.assertRaisesRegex(ValueError, 'invalid output file target'):
                    self.run_job(wire, output=output)
                self.assertEqual(wire.requests, [])

    def test_second_writer_cannot_call_provider(self):
        output = self.root / 'out'
        wire = FaultWire()
        with exclusive_output(output):
            with self.assertRaisesRegex(ValueError, 'another runner'):
                self.run_job(wire)
        self.assertEqual(wire.requests, [])
        self.assertEqual(self.run_job(wire), 0)

    def test_direct_paid_entry_rejects_corrupt_results(self):
        for field, value in (('automatic_pass', False), ('model', 'wrong/model'), ('trace', [])):
            with self.subTest(field=field):
                output = self.root / field
                wire = FaultWire()
                self.assertEqual(self.run_job(wire, output=output), 0)
                row = self.rows(output)[0]; row[field] = value
                (output / 'trials.jsonl').write_text(json.dumps(row) + '\n')
                before = len(wire.requests)
                with self.assertRaises(ValueError): self.run_job(wire, output=output)
                self.assertEqual(len(wire.requests), before)

    def test_generation_settings_cannot_override_job_identity(self):
        config = json.loads((runner.ROOT / 'config/d5_jobs.json').read_text())
        for key, value in (('model', 'wrong/model'), ('messages', []), ('max_tokens', 0), ('top_p', float('nan'))):
            candidate = copy.deepcopy(config); candidate['generation_settings'][key] = value
            with self.assertRaises(ValueError): runner.validate_battery_config(candidate)

    def test_unknown_historical_charge_prevents_final_completion(self):
        wire = FaultWire()
        for count in (1, 69): self.assertEqual(self.run_job(wire, count), 0)
        output = self.root / 'out'
        path = output / 'human_review_annotations.json'
        annotations = json.loads(path.read_text())
        for item in annotations:
            item.update(status='approved', reviewer='SYNTHETIC TEST ONLY',
                        review_note='Temporary annotation for billing-completion regression.')
        path.write_text(json.dumps(annotations))
        rows = self.rows()
        failed = copy.deepcopy(rows[0])
        failed.update(attempt=2, transport_status='transport_failure',
                      halt_reason='transport_error', billing_complete=False)
        rows.append(failed)
        (output / 'trials.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        labels, _ = runner.load_labels()
        runner.write_summary(output, rows, {x['case_id']: x for x in labels})
        self.assertNotEqual(json.loads((output / 'summary.json').read_text())['status'], 'complete')
        self.assertFalse(validate(output, self.lock, allow_incomplete=True)['billing_complete'])
        with self.assertRaisesRegex(ValueError, 'unresolved billing'):
            validate(output, self.lock)


if __name__ == '__main__': unittest.main()

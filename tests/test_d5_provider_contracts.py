"""Provider-request and spending regressions; fake keys/transport, temporary files."""
import copy
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import run_d5_live as runner
from src.live_backend import call_live_model
from test_d5_audit_regressions import WireReplay
from test_d5_runner_contracts import current_lock
from test_d5_team_safety import Response


class ProviderContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lock = self.root / 'test-only-lock.json'
        self.lock.write_text(json.dumps(current_lock()))
        for guard in (
            patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic-provider-check'}),
            patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')),
            patch('socket.getaddrinfo', side_effect=AssertionError('network forbidden')),
        ):
            guard.start()
            self.addCleanup(guard.stop)

    def test_haiku_legacy_combination_rejected_before_transport(self):
        transport = Mock(side_effect=AssertionError('must not construct paid request'))
        with self.assertRaisesRegex(ValueError, 'temperature OR top_p'):
            call_live_model(model='anthropic/claude-haiku-4.5',
                model_input={'system': 'synthetic test'},
                settings={'temperature': 0, 'top_p': 1, 'max_tokens': 4096},
                transport=transport)
        transport.assert_not_called()

    def test_invalid_direct_settings_fail_before_transport(self):
        for settings in ({'temperature': 1.1}, {'temperature': float('nan')},
                         {'max_tokens': True}, {'model': 'different/model'},
                         {'messages': []}, {'provider': {'order': ['unapproved']}}):
            with self.subTest(settings=settings):
                transport = Mock()
                with self.assertRaises(ValueError):
                    call_live_model(model='anthropic/claude-haiku-4.5',
                        model_input={'system': 'synthetic test'}, settings=settings,
                        transport=transport)
                transport.assert_not_called()

    def test_config_rejects_combination_and_haiku_range_for_entire_battery(self):
        config = json.loads((runner.ROOT / 'config/d5_jobs.json').read_text())
        for change in ({'top_p': 1}, {'temperature': 1.1}):
            candidate = copy.deepcopy(config)
            candidate['generation_settings'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner.validate_battery_config(candidate)

    def test_preflight_and_paid_entry_refuse_legacy_config_without_output(self):
        path = runner.ROOT / 'config/d5_jobs.json'
        config = json.loads(path.read_text())
        config['generation_settings']['top_p'] = 1
        original = Path.read_text
        def legacy(current, *args, **kwargs):
            return json.dumps(config) if current == path else original(current, *args, **kwargs)
        for job in range(1, 6):
            for mode in ('preflight', 'paid'):
                with self.subTest(job=job, mode=mode), patch.object(Path, 'read_text', legacy):
                    output = self.root / f'{job}-{mode}'
                    factory = Mock(side_effect=AssertionError('agent must not be created'))
                    args = dict(job_number=job, output=output, lock_path=self.lock, max_new_runs=1)
                    with self.assertRaisesRegex(ValueError, 'omit top_p'):
                        if mode == 'preflight': runner.inspect_live_job(**args)
                        else: runner.run_live_job(**args, agent_factory=factory)
                    factory.assert_not_called()
                    self.assertFalse(output.exists())

    def test_all_jobs_wire_uses_same_two_requested_settings(self):
        settings_seen = []
        class InspectWire(WireReplay):
            def transport(self, request, timeout):
                body = json.loads(request.data)
                settings_seen.append({k: v for k, v in body.items() if k not in ('model', 'messages')})
                return super().transport(request, timeout)
        for job in range(1, 6):
            wire = InspectWire()
            self.assertEqual(runner.run_live_job(job_number=job, output=self.root / f'job-{job}',
                lock_path=self.lock, max_new_runs=1, agent_factory=wire.factory), 0)
            self.assertTrue(wire.requests)
        self.assertTrue(settings_seen)
        self.assertTrue(all(x == {'temperature': 0, 'max_tokens': 4096} for x in settings_seen))

    def test_old_r6_cannot_be_silently_resumed_under_changed_settings(self):
        source = runner.ROOT / 'results/d5/job1-tu-weikang-r6'
        output = self.root / 'old-r6-copy'
        shutil.copytree(source, output)
        before = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
        factory = Mock(side_effect=AssertionError('old r6 must never trigger payment'))
        with self.assertRaises(ValueError):
            runner.run_live_job(job_number=1, output=output, lock_path=self.lock,
                max_new_runs=1, agent_factory=factory)
        factory.assert_not_called()
        self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()})

    def test_late_price_spike_all_jobs_retains_charge_and_stops(self):
        class PriceSpike(WireReplay):
            def __init__(self, position):
                super().__init__(cost=0.00001)
                self.position, self.trial, self.call = position, 0, 0
            def factory(self, **kwargs):
                self.trial += 1
                self.call = 0
                return super().factory(**kwargs)
            def transport(self, request, timeout):
                self.call += 1
                payload = json.loads(super().transport(request, timeout).read())
                if self.trial == self.position:
                    payload['usage']['cost'] = 0.09
                return Response(payload)
        for job in range(1, 6):
            for position in (6, 35, 70):
                with self.subTest(job=job, position=position):
                    output = self.root / f'spike-{job}-{position}'
                    wire = PriceSpike(position)
                    for count in (1, 4, 65):
                        code = runner.run_live_job(job_number=job, output=output,
                            lock_path=self.lock, max_new_runs=count, agent_factory=wire.factory)
                        if code: break
                    rows = [json.loads(s) for s in (output / 'trials.jsonl').read_text().splitlines()]
                    self.assertEqual(code, 4)
                    self.assertEqual((len(rows), wire.trial, wire.call), (position, position, 1))
                    self.assertEqual(rows[-1]['halt_reason'], 'budget_cap')
                    self.assertAlmostEqual(rows[-1]['cost_usd'], 0.09)
                    self.assertTrue(rows[-1]['billing_complete'])
                    self.assertEqual(json.loads((output / 'summary.json').read_text())['status'], 'run_budget_cap')

    def test_cost_above_old_trial_cap_can_continue_within_new_cap(self):
        cases = {row['case_id'] for row in runner.planned_runs()}
        for job in range(1, 6):
            with self.subTest(job=job):
                output = self.root / f'below-new-cap-{job}'
                wire = WireReplay(fail_cases=cases, cost=0.04)
                for count in (1, 4):
                    self.assertEqual(runner.run_live_job(job_number=job, output=output,
                        lock_path=self.lock, max_new_runs=count, agent_factory=wire.factory), 0)
                rows = [json.loads(s) for s in (output / 'trials.jsonl').read_text().splitlines()]
                self.assertEqual(len(rows), 5)
                self.assertTrue(all(row['halt_reason'] == 'final' for row in rows))
                self.assertTrue(all(row['automatic_pass'] is False for row in rows))
                self.assertAlmostEqual(sum(row['cost_usd'] for row in rows), 0.20)

    def test_exact_job_budget_allows_last_reserved_trial_then_stops(self):
        cases = {row['case_id'] for row in runner.planned_runs()}
        for job in range(1, 6):
            with self.subTest(job=job):
                output = self.root / f'exact-budget-{job}'
                wire = WireReplay(fail_cases=cases, cost=0.08)
                for count in (1, 4, 65):
                    code = runner.run_live_job(job_number=job, output=output,
                        lock_path=self.lock, max_new_runs=count, agent_factory=wire.factory)
                    if code: break
                rows = [json.loads(s) for s in (output / 'trials.jsonl').read_text().splitlines()]
                self.assertEqual(code, 4)
                self.assertEqual((len(rows), len(wire.requests)), (35, 35))
                self.assertAlmostEqual(sum(row['cost_usd'] for row in rows), 2.80)
                self.assertEqual(json.loads((output / 'summary.json').read_text())['status'], 'job_budget_cap')
                before = len(wire.requests)
                self.assertEqual(runner.run_live_job(job_number=job, output=output,
                    lock_path=self.lock, max_new_runs=1, agent_factory=wire.factory), 4)
                self.assertEqual(len(wire.requests), before)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Bounded offline audit of the provider boundary, retained r6 and request shapes."""
from __future__ import annotations
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.environ.pop('OPENROUTER_API_KEY', None)
NETWORK_ATTEMPTS = []


def deny_network(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.gethostbyname', 'socket.sendto'}:
        NETWORK_ATTEMPTS.append(event)
        raise RuntimeError('cross-model audit forbids network access')


sys.addaudithook(deny_network)
from scripts import run_d5_live as runner
from scripts.create_d5_lock import canonical, prompt_hashes
from src.claim_agent import ClaimAgent, _State
from src.d4_evaluation import score_trial
from src.live_backend import call_live_model
from test_d5_team_safety import Response

TEST_NAMES = [
    'test_d5_documented_stops',
    'test_d5_team_safety.TeamSafety.test_all_five_jobs_staged_1_4_65_own_keys_and_aggregation',
    'test_d5_team_safety.TeamSafety.test_late_failures_all_jobs_positions_6_35_70',
    'test_d5_provider_contracts.ProviderContracts.test_late_price_spike_all_jobs_retains_charge_and_stops',
    'test_d5_provider_contracts.ProviderContracts.test_exact_job_budget_allows_last_reserved_trial_then_stops',
    'test_d5_team_safety.TeamSafety.test_http_failures_keep_earlier_cost_and_stop',
    'test_d5_team_safety.TeamSafety.test_interrupt_keeps_journal_and_blocks_automatic_replay',
    'test_d5_team_safety.TeamSafety.test_program_error_keeps_returned_response_before_parsing',
    'test_d5_team_safety.TeamSafety.test_append_failure_keeps_scored_row_and_recovers_once',
    'test_d5_team_safety.TeamSafety.test_second_writer_cannot_call_provider',
    'test_live_conversation',
    'test_d5_provider_contracts.ProviderContracts.test_all_jobs_wire_uses_same_two_requested_settings',
    'test_d5_provider_contracts.ProviderContracts.test_haiku_legacy_combination_rejected_before_transport',
    'test_d5_provider_contracts.ProviderContracts.test_old_r6_cannot_be_silently_resumed_under_changed_settings',
    'test_d5_runner_contracts.D5RunnerContracts.test_paid_null_content_is_retained_and_not_retried',
    'test_d5_runner_contracts.D5RunnerContracts.test_all_http_success_malformed_shapes_are_paid_failures',
    'test_d5_runner_contracts.D5RunnerContracts.test_per_run_provider_cost_stops_second_call',
    'test_d5_team_safety.TeamSafety.test_http_200_errors_stop_and_keep_partial_text_and_usage',
    'test_d5_team_safety.TeamSafety.test_unknown_cost_retains_known_lower_bound_blocks_new_spend',
]


def r6_audit():
    directory = ROOT / 'results/d5/job1-tu-weikang-r6'
    rows = [json.loads(s) for s in (directory / 'trials.jsonl').read_text().splitlines()]
    labels, facts = runner.load_labels()
    labelmap = {x['case_id']: x for x in labels}
    claims = {x['claim_id']: x for x in facts['claims']}
    for row in rows:
        score = score_trial(labelmap[row['case_id']], row['decision_record'], claims[row['case_id']], facts,
                            autonomy='confirm', confirmed=True, write_count=row['write_count'], halt_reason=row['halt_reason'])
        assert score['checks'] == row['checks'] and score['passed'] == row['automatic_pass']
    costs = [Decimal(str(r['cost_usd'])) for r in rows]
    assert len(rows) == 70 and all(r['billing_complete'] for r in rows)
    assert all(r['halt_reason'] not in {'paid_malformed_response', 'provider_error', 'budget_cap'} for r in rows)
    assert max(costs) < Decimal('0.035') and sum(costs) < Decimal('2.50')
    return {'trial_count': len(rows), 'original_summary': json.loads((directory / 'summary.json').read_text()),
            'maximum_trial_cost_usd': str(max(costs)), 'total_cost_usd': str(sum(costs)),
            'halt_reasons': dict(Counter(r['halt_reason'] for r in rows)),
            'all_stored_code_checks_reproduced': True, 'new_empty_stop_branch_applicable': False,
            'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.iterdir()) if p.is_file()}}


def request_audit():
    config = json.loads((ROOT / 'config/d5_jobs.json').read_text())
    runner.validate_battery_config(config)
    snapshots = []
    with tempfile.TemporaryDirectory(prefix='d5-wire-audit-') as tmp:
        for number, job in enumerate(config['jobs'], 1):
            agent = ClaimAgent(log_path=Path(tmp) / 'unused.jsonl', descriptor_version=job['prompt_version'])
            # Deliberately use an independently specified completed action/observation.
            state = _State('CLM-8842', 'confirm', True)
            state.trace = [{'Thought': 'fetch'},
                           {'Action': '{"tool":"get_claim","arguments":{"claim_id":"CLM-8842"}}'},
                           {'Observation': {'tool': 'get_claim', 'result': {'found': True, 'claim': {'claim_id': 'CLM-8842'}}}}]
            captured = []
            def transport(request, timeout):
                captured.append(json.loads(request.data))
                return Response({'id': 'synthetic-wire-audit', 'model': job['model'],
                    'choices': [{'message': {'role': 'assistant', 'content': 'Final: audit only'}, 'finish_reason': 'stop'}],
                    'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'cost': 0}})
            with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic-wire-only'}):
                call_live_model(model=job['model'], model_input=agent.model_input(state),
                                settings=config['generation_settings'], transport=transport)
            body = captured[0]
            assert set(body) == {'model', 'messages', 'temperature', 'max_tokens'}
            assert [m['role'] for m in body['messages']] == ['system', 'user', 'assistant', 'user']
            assert body['messages'][-1]['content'].startswith('Observation:')
            task = json.loads(body['messages'][1]['content'].split('\n', 1)[1])
            assert 'history' not in task and 'expected_outcomes' not in task
            snapshots.append({'job': number, **job, 'body_fields': sorted(body),
                'requested_settings': config['generation_settings'],
                'message_roles': [m['role'] for m in body['messages']],
                'messages_sha256': canonical(body['messages']), 'native_tools_sent': False})
    assert len({x['messages_sha256'] for x in snapshots[:4]}) == 1
    assert snapshots[3]['messages_sha256'] != snapshots[4]['messages_sha256']
    return snapshots


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    before = r6_audit()
    requests = request_audit()
    suite = unittest.defaultTestLoader.loadTestsFromNames(TEST_NAMES)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    after = r6_audit()
    report = {'audit_date': '2026-09-06', 'scope': 'offline targeted audit, not live-provider validation',
              'tests_run': result.testsRun, 'tests_passed': result.wasSuccessful(),
              'network_attempts': len(NETWORK_ATTEMPTS), 'paid_model_calls': 0,
              'r6_unchanged': before == after, 'r6': after,
              'runtime_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                 for name in ('src/live_backend.py', 'src/claim_agent.py',
                                              'scripts/d5_safety.py', 'scripts/run_d5_live.py',
                                              'config/d5_jobs.json')},
              'prompt_hashes': prompt_hashes(), 'wire_requests': requests, 'test_selection': TEST_NAMES,
              'full_battery_jobs': [{'job': x['job'], 'model': x['model'], 'prompt_version': x['prompt_version'],
                                     'simulated_trials': 70, 'stages': [1,4,65]} for x in requests],
              'late_fault_scenarios': {'model_or_provider': 60, 'price_spike': 15, 'positions': [6,35,70]}}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('tests_run', 'tests_passed', 'network_attempts', 'paid_model_calls', 'r6_unchanged')}))
    raise SystemExit(not (result.wasSuccessful() and before == after and not NETWORK_ATTEMPTS))


if __name__ == '__main__':
    main()

"""Documented empty completions through the HTTP boundary; no real requests."""
import copy
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_d5_live as runner
from scripts.d5_safety import TrialJournal
from scripts.validate_d5_results import validate
from src.claim_agent import ClaimAgent
from src.live_backend import (PaidMalformedResponse, PaidModelOutputFailure,
                              PaidProviderError, call_live_model)
from test_d5_runner_contracts import current_lock
from test_d5_team_safety import Response


def payload(model, finish='content_filter', cost=0.001, native=None):
    return {'id': 'synthetic-stop', 'model': model,
            'choices': [{'message': {'role': 'assistant', 'content': None},
                         'finish_reason': finish, 'native_finish_reason': native}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'cost': cost}}


class DocumentedStops(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lock = self.root / 'test-only-lock.json'
        self.lock.write_text(json.dumps(current_lock()))
        for guard in (
            patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic-contract-only'}),
            patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')),
            patch('socket.getaddrinfo', side_effect=AssertionError('network forbidden')),
        ):
            guard.start()
            self.addCleanup(guard.stop)

    def call(self, value):
        return call_live_model(model=value['model'], model_input={'system': 'contract check'},
                               settings={'temperature': 0, 'max_tokens': 4096},
                               transport=lambda *a, **k: Response(value))

    def test_explicit_empty_stops_are_model_failures_and_retain_evidence(self):
        for finish, native in [('content_filter', None), ('length', None),
                               ('refusal', None), ('stop', 'refusal')]:
            for content in (None, '', '  '):
                value = payload('anthropic/claude-haiku-4.5', finish, native=native)
                value['choices'][0]['message']['content'] = content
                with self.subTest(finish=finish, native=native, content=content):
                    with self.assertRaises(PaidModelOutputFailure) as caught:
                        self.call(value)
                    self.assertEqual(caught.exception.usage, value['usage'])
                    self.assertEqual(caught.exception.finish_reason, finish)
                    self.assertEqual(caught.exception.native_finish_reason, native)
                    self.assertEqual(caught.exception.text, content)

    def test_unknown_blank_broken_envelope_or_missing_billing_still_stop(self):
        base = payload('google/gemini-2.5-flash-lite')
        variants = []
        p = copy.deepcopy(base); p['choices'][0]['finish_reason'] = 'stop'; variants.append(p)
        p = copy.deepcopy(base); del p['usage']['cost']; variants.append(p)
        p = copy.deepcopy(base); p['choices'][0]['message']['content'] = {}; variants.append(p)
        p = copy.deepcopy(base); del p['choices'][0]['message']['content']; variants.append(p)
        p = copy.deepcopy(base); p['choices'][0]['message']['role'] = 'user'; variants.append(p)
        p = copy.deepcopy(base); p['choices'][0]['finish_reason'] = []; variants.append(p)
        p = copy.deepcopy(base); p['choices'][0]['finish_reason'] = {}; variants.append(p)
        for value in variants:
            with self.assertRaises(PaidMalformedResponse) as caught:
                self.call(value)
            self.assertIs(type(caught.exception), PaidMalformedResponse)

    def test_provider_error_takes_precedence_over_empty_model_stop(self):
        for location in ('top', 'choice'):
            value = payload('anthropic/claude-haiku-4.5')
            target = value if location == 'top' else value['choices'][0]
            target['error'] = {'code': 503, 'message': 'synthetic provider failure'}
            with self.assertRaises(PaidProviderError):
                self.call(value)

    def test_openai_refusal_field_is_preserved_before_scoring(self):
        value = payload('openai/gpt-5-mini', 'stop')
        refusal = 'Synthetic refusal for the contract test.'
        value['choices'][0]['message']['refusal'] = refusal
        journal = TrialJournal(self.root, {'run_id': 'synthetic-refusal'})
        caller = journal.wrap(lambda **kwargs: self.call(value))
        with self.assertRaises(PaidModelOutputFailure) as caught:
            caller(model=value['model'], model_input={'system': 'test'})
        self.assertEqual(caught.exception.refusal, refusal)
        saved = json.loads(journal.path.read_text())
        self.assertEqual(saved['calls'][0]['status'], 'model_output_failure')
        self.assertEqual(saved['calls'][0]['refusal'], refusal)
        self.assertIsNone(saved['calls'][0]['text'])
        self.assertEqual(saved['known_cost_usd'], 0.001)
        for invalid in (None, '', '  ', {}, []):
            value['choices'][0]['message']['refusal'] = invalid
            with self.assertRaises(PaidMalformedResponse) as caught:
                self.call(value)
            self.assertIs(type(caught.exception), PaidMalformedResponse)

    def test_nonempty_content_is_not_rewritten(self):
        value = payload('google/gemini-2.5-flash-lite', 'length')
        value['choices'][0]['message']['content'] = 'I cannot complete this request.'
        self.assertEqual(self.call(value).text, value['choices'][0]['message']['content'])

    def test_all_five_jobs_continue_past_early_and_late_model_stops(self):
        for job in range(1, 6):
            requests = []
            def transport(request, timeout):
                body = json.loads(request.data)
                requests.append(body)
                position = len(requests)
                value = payload(body['model'])
                if position == 6:
                    value['choices'][0]['finish_reason'] = 'length'
                elif position == 35:
                    value['choices'][0].update(finish_reason='stop', native_finish_reason='refusal')
                    if job == 1:
                        value['choices'][0]['native_finish_reason'] = None
                        value['choices'][0]['message']['refusal'] = 'Synthetic OpenAI refusal.'
                elif position not in (2, 70):
                    value['choices'][0].update(finish_reason='stop')
                    value['choices'][0]['message']['content'] = 'Final: no decision provided'
                return Response(value)
            def factory(**kwargs):
                return ClaimAgent(**kwargs, live_caller=lambda **call: call_live_model(**call, transport=transport))
            output = self.root / f'job-{job}'
            for count in (1, 4, 65):
                self.assertEqual(runner.run_live_job(job_number=job, output=output,
                    lock_path=self.lock, max_new_runs=count, agent_factory=factory), 0)
            rows = [json.loads(s) for s in (output / 'trials.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), 70)
            self.assertEqual(len(requests), 70)
            for position in (2, 6, 35, 70):
                row = rows[position - 1]
                self.assertEqual(row['halt_reason'], 'model_output_failure')
                self.assertEqual(row['transport_status'], 'model_response')
                self.assertFalse(row['automatic_pass'])
                self.assertTrue(row['billing_complete'])
                self.assertEqual(row['cost_usd'], 0.001)
            if job == 1:
                self.assertEqual(rows[34]['provider_responses'][0]['refusal'],
                                 'Synthetic OpenAI refusal.')
            self.assertTrue(validate(output, self.lock, allow_incomplete=True)['valid'])
            with self.assertRaisesRegex(ValueError, 'cannot be retried'):
                runner.run_live_job(job_number=job, output=output, lock_path=self.lock,
                    max_new_runs=1, retry_run_id=rows[1]['run_id'], agent_factory=factory)
            self.assertEqual(len(requests), 70)

    def test_empty_completion_cannot_bypass_trial_budget(self):
        for job in range(1, 6):
            calls = []
            def transport(request, timeout):
                body = json.loads(request.data); calls.append(body)
                return Response(payload(body['model'], cost=0.09))
            def factory(**kwargs):
                return ClaimAgent(**kwargs, live_caller=lambda **call: call_live_model(**call, transport=transport))
            output = self.root / f'over-budget-{job}'
            self.assertEqual(runner.run_live_job(job_number=job, output=output,
                lock_path=self.lock, max_new_runs=1, agent_factory=factory), 4)
            row = json.loads((output / 'trials.jsonl').read_text())
            self.assertEqual((row['halt_reason'], row['cost_usd'], len(calls)), ('budget_cap', 0.09, 1))


if __name__ == '__main__':
    unittest.main()

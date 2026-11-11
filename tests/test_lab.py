import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest

from lab.backends.cli import codex_command, claude_command, extract_json, parse_codex, parse_claude
from lab.backends.demo import DemoBackend
from lab.cli import main
from lab.config import ROOT, estimate_cost, load_config
from lab.generate import generate
from lab.report import write_report
from lab.runner import ModeRunner, choose_answer, experiment
from lab.schema import validate_answer
from lab.task import evaluate, load_task, rows_from_solution, solve


class TaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = load_task(ROOT / 'tasks/science-fair-17.json')
        cls.solution = solve(cls.task)[0]
        cls.answer = {'schedule': rows_from_solution(cls.task, cls.solution), 'message': 'C01 supports this.', 'assignments': []}

    def test_shipped_tasks_have_unique_solutions(self):
        expected_ids = {f'science-fair-{seed}' for seed in [17, 29, 43, 59, 71, 83, 97, 109, 127, 149]}
        seen_ids, bundled_solutions = set(), set()
        for path in (ROOT / 'tasks').glob('science-fair-*.json'):
            task = load_task(path)
            seen_ids.add(task['id'])
            solutions = solve(task)
            self.assertEqual(len(solutions), 1, path.name)
            result = evaluate(task, {'schedule': rows_from_solution(task, solutions[0])}, solutions[0])
            self.assertTrue(result['exact'])
            self.assertEqual(result['satisfied_clues'], len(task['clues']))
            if task['id'] in expected_ids:
                self.assertEqual(len(task['clues']), 30, path.name)
                self.assertEqual(task, generate(task['seed']), path.name)
                bundled_solutions.add(json.dumps(solutions[0], sort_keys=True))
        self.assertTrue(expected_ids <= seen_ids, f'Missing bundled cases: {expected_ids - seen_ids}')
        self.assertEqual(len(bundled_solutions), 10, 'Bundled cases must have distinct schedules.')

    def test_generation_is_reproducible_and_unique(self):
        self.assertEqual(generate(77), generate(77))
        self.assertEqual(len(solve(generate(77))), 1)

    def test_correct_schedule_is_exact(self):
        result = evaluate(self.task, self.answer, self.solution)
        self.assertTrue(result['exact'])
        self.assertEqual(result['correct_cells'], 24)

    def test_duplicate_rows_cannot_earn_full_credit(self):
        answer = copy.deepcopy(self.answer)
        answer['schedule'].append(answer['schedule'][0])
        result = evaluate(self.task, answer, self.solution)
        self.assertFalse(result['exact'])
        self.assertLess(result['score'], 100)

    def test_duplicate_values_earn_no_credit(self):
        answer = copy.deepcopy(self.answer)
        answer['schedule'][1]['student'] = answer['schedule'][0]['student']
        result = evaluate(self.task, answer, self.solution)
        self.assertFalse(result['structurally_valid'])
        self.assertEqual(result['correct_cells'], 22)

    def test_missing_or_malformed_answers_score_zero(self):
        for answer in [{}, {'schedule': None}, {'schedule': [42]}, None]:
            self.assertEqual(evaluate(self.task, answer, self.solution)['score'], 0)

    def test_partial_score_counts_cells_not_guess(self):
        answer = copy.deepcopy(self.answer)
        a, b = answer['schedule'][:2]
        a['room'], b['room'] = b['room'], a['room']
        result = evaluate(self.task, answer, self.solution)
        self.assertEqual(result['correct_cells'], 22)
        self.assertFalse(result['exact'])

    def test_solver_cannot_abstain_with_empty_schedule(self):
        with self.assertRaises(ValueError):
            validate_answer({'schedule': [], 'message': 'Unknown', 'assignments': []}, self.task)
        validate_answer({'schedule': [], 'message': 'Plan', 'assignments': []}, self.task, planning=True)

    def test_bad_schema_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_answer({'answer': 'Ada'}, self.task)

    def test_selection_does_not_use_reference_scores(self):
        a = copy.deepcopy(self.answer)
        b = copy.deepcopy(a)
        b['schedule'][0]['room'] = 'wrong'
        records = [{'agent': f'worker-{i}', 'id': str(i), 'answer': value}
                   for i, value in [(1, a), (2, b), (3, b), (4, a)]]
        chosen, votes = choose_answer(records)
        self.assertEqual(chosen, a)  # Tie: worker-1 wins.
        self.assertEqual(votes, ['1', '4'])
        records[3]['answer'] = b
        self.assertEqual(choose_answer(records)[0], b)  # Majority can be wrong.

    def test_row_order_does_not_change_votes(self):
        reverse = copy.deepcopy(self.answer)
        reverse['schedule'].reverse()
        _, votes = choose_answer([{'agent': 'a', 'id': '1', 'answer': self.answer},
                                  {'agent': 'b', 'id': '2', 'answer': reverse}])
        self.assertEqual(votes, ['1', '2'])


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.task = load_task(ROOT / 'tasks/science-fair-17.json')
        self.config = load_config(ROOT / 'configs/classroom.toml')
        self.backend = DemoBackend(self.task)

    async def run_mode(self, mode):
        return await ModeRunner(self.task, self.config, self.backend, mode, progress=lambda _: None).run()

    async def test_independent_cannot_see_peers(self):
        result = await self.run_mode('independent')
        for call in result['calls']:
            self.assertEqual(call['visible_call_ids'], [])
            if call['round'] > 1:
                previous = next(c for c in result['calls'] if c['id'] == call['own_call_id'])
                self.assertEqual(previous['agent'], call['agent'])
                self.assertEqual(previous['round'], call['round'] - 1)

    async def test_exchange_only_sees_previous_round_peers(self):
        result = await self.run_mode('exchange')
        lookup = {c['id']: c for c in result['calls']}
        for call in result['calls']:
            self.assertEqual(len(call['visible_call_ids']), 0 if call['round'] == 1 else 3)
            for ident in call['visible_call_ids']:
                self.assertEqual(lookup[ident]['round'], call['round'] - 1)
                self.assertNotEqual(lookup[ident]['agent'], call['agent'])
            if call['round'] > 1:
                peers = call['prompt'].split('Messages explicitly delivered to you:')[1]
                self.assertNotIn('"schedule"', peers)

    async def test_leader_star_topology_and_call_count(self):
        result = await self.run_mode('leader')
        lookup = {c['id']: c for c in result['calls']}
        self.assertEqual(len(lookup), 13)
        for c in result['calls']:
            for ident in c['visible_call_ids']:
                source = lookup[ident]['agent']
                self.assertTrue(source == 'leader' if c['agent'] != 'leader' else source.startswith('worker'))
        self.assertEqual(result['selected_call_ids'], ['call-013'])

    async def test_wave_budget_does_not_launch_partial_teams(self):
        self.config['budget']['max_calls'] = 5
        result = await self.run_mode('exchange')
        self.assertEqual(len(result['calls']), 4)
        self.assertEqual(result['status'], 'stopped')
        self.assertIn(result['final_answer'], [c['answer'] for c in result['calls']])

    async def test_missing_usage_stops_further_calls(self):
        original = self.backend.call
        async def missing(*args):
            response = await original(*args)
            response['usage'] = None
            return response
        self.backend.call = missing
        result = await self.run_mode('solo')
        self.assertEqual(len(result['calls']), 1)
        self.assertFalse(result['totals']['usage_complete'])
        self.assertEqual(result['status'], 'stopped')

    async def test_malformed_response_still_counts_cost(self):
        original = self.backend.call
        async def malformed(*args):
            response = await original(*args)
            response['text'] = 'not JSON'
            return response
        self.backend.call = malformed
        result = await self.run_mode('solo')
        self.assertEqual(result['totals']['calls'], 1)
        self.assertGreater(result['totals']['estimated_usd'], 0)
        self.assertEqual(result['status'], 'stopped')
        self.assertEqual(result['evaluation']['score'], 0)

    async def test_cost_threshold_stops_next_wave(self):
        self.config['budget']['max_estimated_usd'] = .000001
        result = await self.run_mode('exchange')
        self.assertEqual(result['totals']['calls'], 4)
        self.assertEqual(result['status'], 'stopped')
        self.assertIn('cost', result['stop_reason'])

    async def test_token_threshold_stops_next_wave(self):
        self.config['budget']['max_tokens'] = 1
        result = await self.run_mode('solo')
        self.assertEqual(result['totals']['calls'], 1)
        self.assertIn('token', result['stop_reason'])

    async def test_timeout_is_visible(self):
        async def timeout(*args):
            raise asyncio.TimeoutError()
        self.backend.call = timeout
        result = await self.run_mode('solo')
        self.assertIn('timed out', result['calls'][0]['error'])
        self.assertFalse(result['totals']['usage_complete'])

    async def test_no_scores_or_answer_key_enter_prompts(self):
        result = await self.run_mode('exchange')
        for call in result['calls']:
            self.assertNotIn('correct_cells', call['prompt'])
            self.assertNotIn('evaluation', call['prompt'])
            self.assertNotIn('solutions', call['prompt'])

    async def test_each_completed_mode_is_checkpointed(self):
        checkpoints = []
        await experiment(self.task, self.config, self.backend, ['solo', 'exchange'],
                         progress=lambda _: None, checkpoint=lambda data: checkpoints.append(len(data['results'])))
        self.assertEqual(checkpoints, [1, 2])


class AdapterTests(unittest.TestCase):
    def test_codex_usage_and_final_response(self):
        events = [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': '{"schedule":[]}'}},
                  {'type': 'turn.completed', 'usage': {'input_tokens': 20, 'cached_input_tokens': 10, 'output_tokens': 5}}]
        parsed = parse_codex('\n'.join(json.dumps(e) for e in events))
        self.assertEqual(parsed['usage']['input_tokens'], 20)
        self.assertEqual(parsed['tool_events'], [])
        self.assertEqual(extract_json(parsed['text']), {'schedule': []})

    def test_codex_unexpected_tool_is_rejected_by_parser_audit(self):
        parsed = parse_codex(json.dumps({'type': 'item.completed', 'item': {'type': 'command_execution', 'command': 'ls'}}))
        self.assertEqual(parsed['tool_events'], ['command_execution'])

    def test_codex_disabled_code_mode_diagnostic_is_not_a_tool_call(self):
        parsed = parse_codex(json.dumps({'type': 'item.completed', 'item': {'type': 'error',
            'message': 'Code Mode is unavailable because code-mode host is disabled. Code mode will fail closed; enable it.'}}))
        self.assertEqual(parsed['errors'], [])
        self.assertEqual(parsed['tool_events'], [])
        self.assertEqual(len(parsed['diagnostics']), 1)

    def test_codex_item_errors_fail_closed(self):
        parsed = parse_codex(json.dumps({'type': 'item.completed', 'item': {'type': 'error',
            'message': 'Unrecognized runtime failure'}}))
        self.assertEqual(parsed['errors'], ['Unrecognized runtime failure'])

    def test_codex_errors_are_preserved(self):
        self.assertEqual(parse_codex('{"type":"error","message":"model unavailable"}')['errors'], ['model unavailable'])

    def test_claude_usage_includes_cache_and_cost(self):
        parsed = parse_claude(json.dumps({'result': '{}', 'usage': {'input_tokens': 10, 'cache_read_input_tokens': 20,
            'cache_creation_input_tokens': 5, 'output_tokens': 6}, 'total_cost_usd': .02,
            'modelUsage': {'claude-example': {}}}))
        self.assertEqual(parsed['usage']['input_tokens'], 35)
        self.assertEqual(parsed['usage']['cached_input_tokens'], 20)
        self.assertEqual(parsed['actual_models'], ['claude-example'])
        self.assertEqual(parsed['provider_cost_usd'], .02)

    def test_claude_structured_response(self):
        parsed = parse_claude('{"structured_output":{"schedule":[]},"usage":{"input_tokens":1,"output_tokens":2}}')
        self.assertEqual(extract_json(parsed['text']), {'schedule': []})

    def test_commands_disable_tools_and_do_not_resume(self):
        command = codex_command('cheap-model', Path('/tmp/schema.json'))
        self.assertIn('--ignore-user-config', command)
        self.assertIn('shell_tool', command)
        self.assertIn('multi_agent', command)
        self.assertNotIn('resume', command)
        command = claude_command('haiku', {}, 1)
        self.assertEqual(command[command.index('--tools') + 1], '')
        self.assertIn('--safe-mode', command)
        self.assertNotIn('--fallback-model', command)

    def test_cost_is_based_on_configured_rates(self):
        cost = estimate_cost({'input_tokens': 1_000_000, 'cached_input_tokens': 400_000, 'output_tokens': 10_000},
                             {'input_per_million': 5, 'cached_input_per_million': 1, 'output_per_million': 20})
        self.assertAlmostEqual(cost, 3.6)

    def test_report_does_not_allow_script_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.html'
            write_report({'title': '</script><script>alert(1)</script>'}, path)
            text = path.read_text()
            self.assertNotIn('</script><script>alert(1)', text)
            self.assertIn('\\u003c/script', text)

    def test_config_rejects_nan_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.toml'
            original = (ROOT / 'configs/classroom.toml').read_text()
            path.write_text(original.replace('max_estimated_usd = 3.0', 'max_estimated_usd = nan'))
            with self.assertRaises(ValueError):
                load_config(path)


if __name__ == '__main__':
    unittest.main()

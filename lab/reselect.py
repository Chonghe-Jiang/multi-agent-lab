"""Re-evaluate candidate selection using existing responses, with zero model calls."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path

from .diagnostics import annotate_result
from .report import write_report
from .selection import SELECTIONS, choose_answer
from .storage import atomic_json
from .suite_report import write_suite_summary
from .task import evaluate, solve


def reselect_recording(data, selection):
    if selection not in SELECTIONS:
        raise ValueError('Unknown selection rule.')
    output = copy.deepcopy(data)
    output['offline_reselection'] = {'selection': selection, 'created_at': datetime.now(timezone.utc).isoformat(),
        'new_model_calls': 0, 'scope': 'Final candidate selection only; agent messages are unchanged.'}
    task = output['task']
    solutions = solve(task)
    if len(solutions) != 1:
        raise ValueError('Recording task must have exactly one solution.')
    for result in output['results']:
        before = evaluate(task, result.get('final_answer') or {}, solutions[0])
        original_rule = result.get('selection', 'plurality' if result['mode'] in ('independent', 'exchange') else 'native')
        if result['mode'] in ('independent', 'exchange'):
            pool = []
            for turn in sorted({c['round'] for c in result['calls']}, reverse=True):
                group = [c for c in result['calls'] if c['round'] == turn and c.get('answer') and c['status'] == 'ok']
                if len(group) == 4 and len({c['agent'] for c in group}) == 4:
                    pool = group
                    break
            if pool:
                result['final_answer'], result['selected_call_ids'] = choose_answer(pool, task, selection)
            result['selection'] = selection
        else:
            result['selection'] = 'native'
        result['evaluation'] = evaluate(task, result.get('final_answer') or {}, solutions[0])
        result['selection_comparison'] = {'before_rule': original_rule, 'before_score': before['score'],
            'before_exact': before['exact'], 'after_rule': result['selection'],
            'after_score': result['evaluation']['score'], 'after_exact': result['evaluation']['exact']}
        annotate_result(task, result, solutions[0])
    return output


def reselect_path(source, out, selection='public-checker'):
    source, out = Path(source), Path(out)
    if source.is_dir() and out.resolve().is_relative_to(source.resolve()):
        raise ValueError('Choose a reselection output directory outside the source directory.')
    recordings = sorted(source.rglob('experiment.json')) if source.is_dir() else [source]
    if not recordings:
        raise ValueError('No experiment.json recordings were found.')
    # Validate every input before creating any output.
    loaded = [reselect_recording(json.loads(path.read_text()), selection) for path in recordings]
    identities, source_tasks = set(), {}
    for data in loaded:
        task = data['task']
        task_id = task['id']
        if not isinstance(task_id, str) or not task_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in task_id):
            raise ValueError('Unsafe recording task ID.')
        if task_id in source_tasks and source_tasks[task_id] != task:
            raise ValueError('Conflicting task contents for one task ID.')
        source_tasks[task_id] = task
        for result in data['results']:
            repeat = result.get('repeat', 1)
            if type(repeat) is not int or repeat < 1:
                raise ValueError('Recorded repeat numbers must be positive integers.')
            if result['mode'] not in ('solo', 'solo-budget', 'leader', 'independent', 'exchange'):
                raise ValueError('Unknown recorded mode.')
            identity = (task_id, repeat, result['mode'])
            if identity in identities:
                raise ValueError('Duplicate task/repeat/mode recordings. Select one source suite.')
            identities.add(identity)
    out.mkdir(parents=True, exist_ok=False)
    tasks, modes, jobs, states = {}, [], [], {}
    for data in loaded:
        task = data['task']; tasks[task['id']] = task
        for result in data['results']:
            repeat = result.get('repeat', 1)
            if result['mode'] not in modes:
                modes.append(result['mode'])
            key = f"{task['id']}/repeat-{repeat:03d}/{result['mode']}"
            jobs.append({'key': key, 'task_id': task['id'], 'repeat': repeat, 'mode': result['mode']})
            states[key] = {'result': result}
        for repeat in {r.get('repeat', 1) for r in data['results']}:
            folder = out / task['id'] / f'repeat-{repeat:03d}'
            folder.mkdir(parents=True, exist_ok=True)
            subset = {**data, 'results': [r for r in data['results'] if r.get('repeat', 1) == repeat]}
            atomic_json(folder / 'experiment.json', subset)
            write_report(subset, folder / 'report.html')
    manifest = {'created_at': loaded[0]['offline_reselection']['created_at'],
        'offline_reselection': {'selection': selection, 'source': str(source.resolve()), 'new_model_calls': 0},
        'tasks': list(tasks.values()), 'modes': modes, 'jobs': jobs,
        'source': {'recording_source': str(source.resolve())}, 'config': loaded[0]['config'],
        'synthetic': all(d.get('synthetic', False) for d in loaded),
        'requested_model': loaded[0]['results'][0]['requested_model'] if loaded[0]['results'] else 'unknown'}
    atomic_json(out / 'manifest.json', manifest)
    write_suite_summary(out, manifest, states, 0)
    rows = []
    for key, state in states.items():
        r = state['result']
        rows.append({'job': key, **r['selection_comparison']})
    atomic_json(out / 'selection-comparison.json', rows)
    return json.loads((out / 'summary.json').read_text())

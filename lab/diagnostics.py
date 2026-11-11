"""Post-run teaching diagnostics. These values never enter model prompts."""
from collections import Counter

from .selection import choose_answer, schedule_key
from .task import check_candidate, evaluate, solve


def annotate_result(task, result, solution=None):
    solution = solution or solve(task, limit=1)[0]
    calls = result['calls']
    lookup = {c['id']: c for c in calls}
    revisions = {'improved': 0, 'worsened': 0, 'unchanged': 0}
    for c in calls:
        if not c.get('answer'):
            continue
        c['evaluation'] = evaluate(task, c['answer'], solution)
        c['public_check'] = check_candidate(task, c['answer'])
        prev = lookup.get(c.get('own_call_id'))
        if prev and prev.get('answer') and len(prev['answer']['schedule']) == len(task['slots']):
            delta = c['evaluation']['correct_cells'] - prev['evaluation']['correct_cells']
            revisions['improved' if delta > 0 else 'worsened' if delta < 0 else 'unchanged'] += 1
    last = {}
    for c in calls:
        if c.get('answer') and len(c['answer']['schedule']) == len(task['slots']):
            last[c['agent']] = c
    workers = [c for agent, c in last.items() if agent.startswith('worker')]
    votes = Counter(schedule_key(c) for c in workers)
    counts = sorted(votes.values(), reverse=True)
    best = max((c['evaluation']['score'] for c in workers), default=None)
    curves = []
    for turn in sorted({c['round'] for c in calls if c['round'] > 0}):
        group = [c for c in calls if c['round'] == turn and c.get('answer')]
        if result['mode'] == 'leader':
            selected = next((c['answer'] for c in group if c['agent'] == 'leader'), None)
        elif result['mode'] in ('solo', 'solo-budget'):
            selected = group[0]['answer'] if group else None
        else:
            if len(group) != 4:
                continue
            selected, _ = choose_answer(group, task, result.get('selection', 'plurality'))
        if selected is None:
            continue
        prefix = [c for c in calls if c['round'] <= turn]
        known = [c['usage'] for c in prefix if c.get('usage')]
        curves.append({'round': turn, 'score': evaluate(task, selected, solution)['score'],
                       'tokens': sum(u['input_tokens'] + u['output_tokens'] for u in known),
                       'usage_complete': len(known) == len(prefix)})
    score = result['evaluation']['score']
    result['diagnostics'] = {'revisions': revisions, 'final_vote_counts': counts,
        'plurality_tie': len(counts) > 1 and counts[0] == counts[1] if workers else False,
        'best_final_worker_score': best,
        'best_any_worker_score': max((c['evaluation']['score'] for c in calls if c['agent'].startswith('worker') and c.get('evaluation')), default=None),
        'selection_gap': round(best - score, 2) if best is not None else None,
        'correct_worker_lost': any(c['evaluation']['exact'] for c in workers) and not result['evaluation']['exact'],
        'round_curve': curves}
    return result

"""Candidate selection uses public constraints only. No solver or answer key."""
from collections import Counter
import json

from .task import check_candidate

SELECTIONS = ('plurality', 'public-checker')


def schedule_key(record):
    return json.dumps(sorted(record['answer']['schedule'], key=lambda r: r['slot']), sort_keys=True)


def choose_answer(results, task=None, selection='plurality'):
    if selection not in SELECTIONS:
        raise ValueError(f'Unknown selection rule: {selection}')
    candidates = sorted((r for r in results if r and r.get('answer')), key=lambda r: r['agent'])
    if not candidates:
        return None, []
    counts = Counter(schedule_key(r) for r in candidates)
    if selection == 'public-checker':
        if task is None:
            raise ValueError('public-checker requires the public task.')
        def rank(record):
            checks = check_candidate(task, record['answer'])
            return (checks['structurally_valid'], checks['satisfied_clues'], counts[schedule_key(record)])
    else:
        def rank(record):
            return counts[schedule_key(record)]
    # Stable agent order breaks ties. Never inspect reference scores.
    winner = max(candidates, key=rank)
    return winner['answer'], [r['id'] for r in candidates if schedule_key(r) == schedule_key(winner)]

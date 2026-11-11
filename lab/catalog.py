"""The active classroom set is explicit; legacy cases remain available."""
import json
from pathlib import Path

from .config import ROOT
from .task import load_task

DEFAULT_TASK = ROOT / 'tasks/science-fair-easy-201.json'
DEFAULT_CATALOG = ROOT / 'tasks/catalog.json'


def load_catalog(path=DEFAULT_CATALOG, difficulty=None):
    path = Path(path)
    raw = json.loads(path.read_text(encoding='utf-8'))
    tasks = []
    seen = set()
    for entry in raw['tasks']:
        if difficulty and entry['difficulty'] != difficulty:
            continue
        task = load_task(path.parent / entry['file'])
        if task['id'] in seen:
            raise ValueError('Catalog task IDs must be unique.')
        seen.add(task['id'])
        task['difficulty'] = entry['difficulty']
        task['calibration'] = raw['calibration']
        tasks.append(task)
    if not tasks:
        raise ValueError('No tasks match the selected catalog and difficulty.')
    return tasks

"""A reproducible suite with per-call journals and safe process-level resume."""
import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

from .backends.cli import CLIBackend
from .backends.demo import DemoBackend
from .config import ROOT
from .report import write_report
from .runner import ALL_MODES, ModeRunner
from .storage import atomic_json, suite_lock
from .task import solve
from .suite_report import write_suite_summary


def source_metadata():
    files = sorted((ROOT / 'lab').rglob('*.py')) + sorted((ROOT / 'lab').glob('*.html'))
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    commit, dirty = None, None
    with suppress(OSError, subprocess.CalledProcessError):
        commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                         stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain', '--', 'lab'], text=True).strip())
    return {'code_sha256': digest.hexdigest(), 'git_commit': commit, 'git_dirty': dirty}


def job_list(tasks, modes, repeats):
    jobs = []
    for repeat in range(1, repeats + 1):
        for index, task in enumerate(tasks):
            shift = (index + repeat - 1) % len(modes)
            for mode in list(modes)[shift:] + list(modes)[:shift]:
                key = f"{task['id']}/repeat-{repeat:03d}/{mode}"
                jobs.append({'key': key, 'task_id': task['id'], 'mode': mode, 'repeat': repeat})
    return jobs


def manifest_for(tasks, config, backend, modes, repeats, parallel_cases):
    source = source_metadata()
    identity = {'tasks': tasks, 'config': config, 'backend': backend.name,
                'requested_model': backend.model, 'backend_version': backend.version,
                'modes': list(modes), 'repeats': repeats, 'parallel_cases': parallel_cases,
                'code_sha256': source['code_sha256']}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return {**identity, 'fingerprint': fingerprint, 'source': source,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'jobs': job_list(tasks, modes, repeats), 'synthetic': backend.name == 'demo'}


async def run_suite(tasks, config, backend_name, model, out, modes=ALL_MODES, repeats=1,
                    resume=False, parallel_cases=1, progress=print, backend_factory=None):
    out = Path(out)
    if not tasks or not modes or len(set(modes)) != len(modes) or any(m not in ALL_MODES for m in modes):
        raise ValueError('Select tasks and distinct supported modes.')
    if type(repeats) is not int or repeats < 1 or type(parallel_cases) is not int or not 1 <= parallel_cases <= 4:
        raise ValueError('repeats must be positive; parallel_cases must be 1 through 4.')
    if len({t['id'] for t in tasks}) != len(tasks):
        raise ValueError('Suite task IDs must be unique.')
    for task in tasks:
        if not isinstance(task['id'], str) or not task['id'] or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in task['id']):
            raise ValueError('Task IDs must contain only letters, numbers, hyphens, or underscores.')
        if len(solve(task)) != 1:
            raise ValueError(f"Task is not uniquely solvable: {task['id']}")
    backend = (backend_factory(tasks[0]) if backend_factory else
               DemoBackend(tasks[0]) if backend_name == 'demo' else CLIBackend(backend_name, model))
    proposed = manifest_for(tasks, config, backend, modes, repeats, parallel_cases)
    if resume:
        if not (out / 'manifest.json').is_file():
            raise ValueError('--resume requires a saved suite manifest.')
    else:
        out.mkdir(parents=True, exist_ok=False)
    with suite_lock(out):
        if resume:
            manifest = json.loads((out / 'manifest.json').read_text())
            if manifest['fingerprint'] != proposed['fingerprint']:
                raise ValueError('Resume configuration, tasks, backend version, or source code differs. Use the original setup or a new directory.')
        else:
            manifest = proposed
            atomic_json(out / 'manifest.json', manifest)
        states = {}
        for job in manifest['jobs']:
            path = out / job['key'] / 'state.json'
            if path.is_file():
                states[job['key']] = json.loads(path.read_text())
        # Persisted prior wall time is separate from per-mode active time budgets.
        prior = json.loads((out / 'summary.json').read_text()).get('suite_seconds', 0) if (out / 'summary.json').exists() else 0
        started = time.monotonic()
        def refresh():
            write_suite_summary(out, manifest, states, prior + time.monotonic() - started)
        refresh()
        semaphore = asyncio.Semaphore(parallel_cases)
        async def case_run(task, repeat):
            async with semaphore:
                local_backend = backend_factory(task) if backend_factory else DemoBackend(task) if backend_name == 'demo' else backend
                jobs = [j for j in manifest['jobs'] if j['task_id'] == task['id'] and j['repeat'] == repeat]
                folder = out / task['id'] / f'repeat-{repeat:03d}'
                folder.mkdir(parents=True, exist_ok=True)
                def case_report():
                    results = [states[j['key']]['result'] for j in jobs if states.get(j['key'], {}).get('result')]
                    data = {'format_version': 2, 'created_at': manifest['created_at'], 'synthetic': manifest['synthetic'],
                            'source': manifest['source'], 'task': task, 'config': config, 'results': results}
                    atomic_json(folder / 'experiment.json', data)
                    write_report(data, folder / 'report.html')
                for job in jobs:
                    key = job['key']
                    saved = states.get(key, {})
                    if saved.get('result'):
                        progress(f"Resume: kept terminal result {key}")
                        continue
                    path = out / key / 'state.json'
                    def checkpoint(state):
                        states[key] = state
                        atomic_json(path, state)
                    runner = ModeRunner(task, config, local_backend, job['mode'], repeat,
                        lambda text: progress(f"[{task['id']}] {text}"), saved_state=saved, call_checkpoint=checkpoint)
                    result = await runner.run()
                    states[key] = {'calls': result['calls'], 'elapsed_seconds': result['elapsed_seconds'], 'result': result}
                    atomic_json(path, states[key])
                    case_report()
                    refresh()
                    progress(f"Finished {key}: {result['status']}, {result['evaluation']['score']}%")
                case_report()
        try:
            await asyncio.gather(*(case_run(t, r) for r in range(1, repeats + 1) for t in tasks))
        finally:
            refresh()
        return json.loads((out / 'summary.json').read_text())

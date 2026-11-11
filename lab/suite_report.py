"""Static suite dashboard and CSV. This module never starts a model call."""
import csv
import html
import statistics
from pathlib import Path

from .storage import atomic_json


def write_suite_summary(out, manifest, states, suite_seconds):
    out = Path(out)
    rows = []
    for job in manifest['jobs']:
        result = states.get(job['key'], {}).get('result')
        if not result:
            continue
        totals = result['totals']
        diagnostics = result.get('diagnostics', {})
        task = next(t for t in manifest['tasks'] if t['id'] == job['task_id'])
        rows.append({'task': job['task_id'], 'difficulty': task.get('difficulty', 'unrated'),
            'mode': job['mode'], 'repeat': job['repeat'], 'status': result['status'],
            'score': result['evaluation']['score'], 'exact': result['evaluation']['exact'],
            'calls': totals['calls'], 'tokens': totals['input_tokens'] + totals['output_tokens'],
            'usage_complete': totals['usage_complete'], 'seconds': result['elapsed_seconds'],
            'accounting_estimate_usd': totals['estimated_usd'], 'provider_reported_usd': totals['provider_reported_usd'],
            'stop_reason': result['stop_reason'], 'selection': result.get('selection', 'native'),
            'plurality_tie': diagnostics.get('plurality_tie', False) if job['mode'] in ('independent', 'exchange') else False,
            'correct_worker_lost': diagnostics.get('correct_worker_lost', False),
            'report': f"{job['task_id']}/repeat-{job['repeat']:03d}/report.html"})
    groups = {}
    for mode in manifest['modes']:
        selected = [r for r in rows if r['mode'] == mode]
        complete = [r for r in selected if r['status'] == 'complete']
        groups[mode] = {'recorded': len(selected), 'complete': len(complete),
            'stopped': len(selected) - len(complete), 'exact': sum(r['exact'] for r in complete),
            'mean_score': statistics.mean(r['score'] for r in complete) if complete else None,
            'total_tokens': sum(r['tokens'] for r in selected),
            'unknown_usage_runs': sum(not r['usage_complete'] for r in selected),
            'calls': sum(r['calls'] for r in selected), 'ties': sum(r['plurality_tie'] for r in complete),
            'correct_worker_lost': sum(r['correct_worker_lost'] for r in complete)}
    inflight = [c for state in states.values() if not state.get('result') for c in state.get('calls', [])]
    summary = {'format_version': 2, 'created_at': manifest['created_at'], 'source': manifest['source'],
        'synthetic': manifest['synthetic'], 'offline_reselection': manifest.get('offline_reselection'),
        'requested_model': manifest['requested_model'], 'planned_runs': len(manifest['jobs']),
        'recorded_runs': len(rows), 'suite_seconds': suite_seconds, 'by_mode': groups, 'results': rows,
        'incomplete_job_calls': len(inflight),
        'incomplete_job_known_tokens': sum(c['usage']['input_tokens'] + c['usage']['output_tokens'] for c in inflight if c.get('usage'))}
    atomic_json(out / 'summary.json', summary)
    tmp = out / 'summary.csv.tmp'
    with tmp.open('w', newline='', encoding='utf-8') as handle:
        fields = list(rows[0]) if rows else ['task', 'mode', 'status', 'score']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    tmp.replace(out / 'summary.csv')
    e = html.escape
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Suite results · Multi-Agent Lab</title><style>body{margin:0;background:#f5f5ee;color:#18312f;font:15px/1.6 system-ui}main{max-width:1160px;margin:35px auto;padding:22px;border-top:5px solid #087f6c}h1{font-size:38px;letter-spacing:-.04em}table{width:100%;border-collapse:collapse;background:white}td,th{padding:10px;border-bottom:1px solid #d6dfd9;text-align:left}th{font-size:12px}.scroll{overflow:auto}.notice{background:#fff0dc;padding:12px 16px;border-left:4px solid #a34b16}a{color:#087f6c}</style><main><h1>Classroom suite results</h1>'''
    page += f'<p>{len(rows)}/{len(manifest["jobs"])} runs recorded · model: {e(manifest["requested_model"])} · {suite_seconds/60:.1f} minutes of controller wall time</p>'
    if manifest['synthetic']:
        page += '<p class="notice">SYNTHETIC DEMONSTRATION. No model calls or charges. Scores and usage are scripted examples.</p>'
    if manifest.get('offline_reselection'):
        page += '<p class="notice">OFFLINE RESELECTION. Existing candidate answers were selected again. No model calls were made. Recorded usage belongs to the original runs.</p>'
    page += '<p>Equal ceilings do not imply equal spending. Solo-budget adds a longer single-agent baseline. Compare observed tokens and scores.</p>'
    page += '<h2>Aggregate results</h2><div class="scroll"><table><tr><th>Mode</th><th>Complete / recorded</th><th>Mean score</th><th>Exact</th><th>Calls</th><th>Known tokens</th><th>Plurality ties</th><th>Correct worker lost</th></tr>'
    for mode, g in groups.items():
        score = 'Pending' if g['mean_score'] is None else f"{g['mean_score']:.2f}%"
        tokens = f"{g['total_tokens']:,}" + (' + unknown' if g['unknown_usage_runs'] else '')
        page += f'<tr><td>{e(mode)}</td><td>{g["complete"]}/{g["recorded"]}</td><td>{score}</td><td>{g["exact"]}</td><td>{g["calls"]}</td><td>{tokens}</td><td>{g["ties"]}</td><td>{g["correct_worker_lost"]}</td></tr>'
    page += '</table></div><p>Mean scores and exact counts use complete runs. Stopped runs remain in the detail table and CSV.</p>'
    page += '<h2>Individual runs</h2><div class="scroll"><table><tr><th>Case / repeat</th><th>Level</th><th>Mode</th><th>Status</th><th>Score</th><th>Selection</th><th>Known tokens</th></tr>'
    for r in rows:
        page += f'<tr><td><a href="{e(r["report"])}">{e(r["task"])} / {r["repeat"]}</a></td><td>{e(r["difficulty"])}</td><td>{e(r["mode"])}</td><td>{e(r["status"])}</td><td>{r["score"]:.2f}%</td><td>{e(r["selection"])}</td><td>{r["tokens"]:,}'+(' + unknown' if not r['usage_complete'] else '')+'</td></tr>'
    page += '</table></div><p>Difficulty levels describe structure. They are not calibrated model success rates. Repeated trials are needed for comparisons.</p>'
    if inflight:
        page += f'<p class="notice">Incomplete jobs contain {len(inflight)} journaled calls. Their usage is listed separately in summary.json.</p>'
    page += '<p>Dollar accounting uses configured assumptions. Provider-reported dollars can be unknown. Active calls can exceed stop thresholds.</p><p><a href="summary.csv">CSV</a> · <a href="summary.json">Summary JSON</a> · <a href="manifest.json">Configuration and source manifest</a></p></main></html>'
    tmp = out / 'index.html.tmp'; tmp.write_text(page, encoding='utf-8'); tmp.replace(out / 'index.html')

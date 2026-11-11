# Suite checkpoints and recovery

Start a suite with a new output directory:

```bash
python -m lab suite --backend codex --out runs/study
```

Continue it with the saved configuration:

```bash
python -m lab suite --resume --out runs/study
```

The manifest stores task contents, configuration, selected modes, repeats, backend version, and a source-code digest.

Resume rejects changes to this identity. Source matching includes report code, so use the original checkout for recovery.

A file lock prevents two controllers from using the same output directory. The operating system releases the lock after process exit.

## Saved calls

Each mode has a `state.json` journal. The controller saves `running` before it starts a model process.

It saves the response, usage, and status after the call. JSON writes use atomic replacement and filesystem synchronization.

Saved successful responses are replayed locally. The controller reconstructs permitted context and launches only missing calls.

The per-mode elapsed budget carries across resume. Paused wall time does not consume that active-time budget.

Terminal mode results are kept, including stopped modes. Resume continues the remaining jobs.

## Unknown outcomes

A process can stop after the provider charges for a call but before its response reaches the journal.

A saved `running` call therefore has an unknown billing outcome. Resume marks that mode as stopped and launches no remaining wave members.

It does not retry that call. Its usage stays unknown. Other suite jobs continue.

For an intentional new attempt, use a new output directory. The provider can charge for both attempts.

The journal prevents silent automatic retries after a process interruption. It cannot guarantee billing state after storage loss or provider-side failures.

## Output files

- `index.html`: suite scores, resource use, and links to per-case reports.
- `summary.csv` and `summary.json`: terminal results and incomplete-job accounting.
- `manifest.json`: the saved experiment identity.
- `<task>/repeat-NNN/<mode>/state.json`: durable per-call journal and terminal result.
- `<task>/repeat-NNN/experiment.json` and `report.html`: the case recording and interactive report.

Pending jobs appear in the planned-run count. Incomplete-call accounting remains separate from terminal-result totals.

The dollar figures use configured assumptions. Unknown usage and unknown provider cost are never treated as zero charges.

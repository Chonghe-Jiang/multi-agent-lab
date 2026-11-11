import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import uuid

from .backends.cli import CLIBackend
from .backends.demo import DemoBackend
from .config import ROOT, load_config
from .catalog import DEFAULT_TASK, DEFAULT_CATALOG, load_catalog
from .selection import SELECTIONS
from .suite import run_suite
from .reselect import reselect_path
from .generate import generate
from .report import write_report
from .runner import ALL_MODES, experiment
from .task import load_task, public_prompt, solve


def parser():
    p = argparse.ArgumentParser(description="Compare agent collaboration structures in a classroom.")
    sub = p.add_subparsers(dest="command", required=True)
    for name, help_text in [("demo", "Run a free, clearly labeled synthetic demonstration."),
                            ("compare", "Compare collaboration modes and the longer solo baseline."),
                            ("run", "Run one collaboration mode with a real CLI backend.")]:
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--task", type=Path, default=DEFAULT_TASK)
        cmd.add_argument("--config", type=Path, default=ROOT / "configs/classroom.toml")
        cmd.add_argument("--out", type=Path)
        cmd.add_argument("--repeats", type=int, default=1)
        cmd.add_argument("--selection", choices=SELECTIONS)
        cmd.add_argument("--solo-rounds", type=int)
        if name != "run":
            cmd.add_argument("--modes", nargs="+", choices=ALL_MODES, default=list(ALL_MODES))
        cmd.add_argument("--rounds", type=int, help="Override rounds per agent (leader adds coordination calls).")
        if name != "demo":
            cmd.add_argument("--backend", choices=["codex", "claude"], default="codex")
            cmd.add_argument("--model", help="Explicit model override. There is no automatic expensive fallback.")
        if name == "run":
            cmd.add_argument("--mode", choices=ALL_MODES, required=True)
    suite = sub.add_parser("suite", help="Run or resume a catalog with per-call checkpoints.")
    suite.add_argument("--backend", choices=["codex", "claude", "demo"])
    suite.add_argument("--model")
    suite.add_argument("--catalog", type=Path)
    suite.add_argument("--difficulty", choices=["easy", "medium", "hard"])
    suite.add_argument("--config", type=Path)
    suite.add_argument("--modes", nargs="+", choices=ALL_MODES)
    suite.add_argument("--selection", choices=SELECTIONS)
    suite.add_argument("--repeats", type=int)
    suite.add_argument("--parallel-cases", type=int)
    suite.add_argument("--out", type=Path, required=True)
    suite.add_argument("--resume", action="store_true")
    listing = sub.add_parser("list", help="List the active classroom catalog.")
    listing.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    listing.add_argument("--difficulty", choices=["easy", "medium", "hard"])
    reselection = sub.add_parser("reselect", help="Compare selection rules offline, with zero model calls.")
    reselection.add_argument("recording", type=Path)
    reselection.add_argument("--selection", choices=SELECTIONS, default="public-checker")
    reselection.add_argument("--out", type=Path, required=True)
    replay = sub.add_parser("replay", help="Build an HTML report from an existing experiment JSON file.")
    replay.add_argument("recording", type=Path)
    replay.add_argument("--out", type=Path, default=Path("runs/replay.html"))
    task = sub.add_parser("task", help="Print the public case file.")
    task.add_argument("--task", type=Path, default=DEFAULT_TASK)
    new = sub.add_parser("new-task", help="Generate another uniquely solvable case.")
    new.add_argument("--difficulty", choices=["easy", "medium", "hard"], default="medium")
    new.add_argument("--seed", type=int, required=True)
    new.add_argument("--out", type=Path, required=True)
    sub.add_parser("doctor", help="Check Python and CLI installations without model calls.")
    return p


def save(data, output):
    recording = output / "experiment.json.tmp"
    recording.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    recording.replace(output / "experiment.json")
    report = output / "report.html.tmp"
    write_report(data, report)
    report.replace(output / "report.html")
    print(f"\nReport: {(output / 'report.html').resolve()}")
    print(f"Recording: {(output / 'experiment.json').resolve()}")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    args = parser().parse_args(argv)
    try:
        if args.command == "list":
            for task in load_catalog(args.catalog, args.difficulty):
                print(f"{task['id']:30} {task['difficulty']:6} {len(task['slots'])} visits  "
                      f"{len(task['categories'])} categories  {len(task['clues'])} clues")
            print("Levels describe structure; model success rates need live calibration.")
            return 0
        if args.command == "reselect":
            summary = reselect_path(args.recording, args.out, args.selection)
            print(f"Offline reselection: {summary['recorded_runs']} recorded runs; zero new model calls.")
            print(f"Report: {(args.out / 'index.html').resolve()}")
            return 0
        if args.command == "suite":
            saved = json.loads((args.out / 'manifest.json').read_text()) if args.resume else {}
            tasks = load_catalog(args.catalog or DEFAULT_CATALOG, args.difficulty) if args.catalog or args.difficulty else saved.get('tasks') or load_catalog()
            config = load_config(args.config) if args.config else saved.get('config') or load_config(ROOT / 'configs/classroom.toml')
            if args.selection:
                config['selection'] = args.selection
            backend_name = args.backend or saved.get('backend') or 'codex'
            model = args.model or saved.get('requested_model') or (config['models'].get(backend_name) if backend_name != 'demo' else 'synthetic-fixture')
            modes = args.modes or saved.get('modes') or list(ALL_MODES)
            repeats = args.repeats if args.repeats is not None else saved.get('repeats', 1)
            parallel = args.parallel_cases if args.parallel_cases is not None else saved.get('parallel_cases', 1)
            planned = len(tasks) * len(modes) * repeats
            print(f"Suite: {len(tasks)} cases, {planned} mode runs; backend={backend_name}, model={model}.")
            print(f"Each run: {config['budget']['max_calls']} calls; {config['budget']['max_tokens']:,} token stop threshold.")
            print(f"Original planned accounting thresholds: ${planned * config['budget']['max_estimated_usd']:.2f}; estimates can overshoot.")
            print("Resume keeps terminal results and reuses saved calls. Ambiguous interrupted calls are not retried.")
            summary = asyncio.run(run_suite(tasks, config, backend_name, model, args.out, modes, repeats, args.resume, parallel))
            print(f"Report: {(args.out / 'index.html').resolve()}")
            return 1 if any(g['stopped'] for g in summary['by_mode'].values()) else 0
        if args.command == "doctor":
            print(f"Python {sys.version.split()[0]} (requires 3.11+)")
            for name in ["codex", "claude"]:
                print(f"{name}: {shutil.which(name) or 'not installed'}")
            print("Free demo: python -m lab demo\nAuthentication: codex login OR claude auth login")
            return 0
        if args.command == "replay":
            data = json.loads(args.recording.read_text(encoding="utf-8"))
            args.out.parent.mkdir(parents=True, exist_ok=True)
            write_report(data, args.out)
            print(f"Report: {args.out.resolve()}")
            return 0
        if args.command == "new-task":
            task = generate(args.seed, args.difficulty)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
            print(f"Created {args.out}: {len(task['clues'])} clues, exactly one solution.")
            return 0
        task = load_task(args.task)
        if args.command == "task":
            print(public_prompt(task))
            return 0
        config = load_config(args.config)
        if args.selection:
            config["selection"] = args.selection
        if args.solo_rounds is not None:
            if args.solo_rounds < 1:
                raise ValueError("--solo-rounds must be positive.")
            config["solo_budget_rounds"] = args.solo_rounds
        if args.rounds is not None:
            if args.rounds < 1:
                raise ValueError("--rounds must be positive.")
            config["rounds"] = args.rounds
        modes = [args.mode] if args.command == "run" else args.modes
        if len(set(modes)) != len(modes):
            raise ValueError("Select each mode once.")
        if args.repeats < 1:
            raise ValueError("--repeats must be positive.")
        if len(solve(task)) != 1:
            raise ValueError("Task must have exactly one solution.")
        backend = DemoBackend(task) if args.command == "demo" else CLIBackend(args.backend, args.model or config["models"][args.backend])
        count = len(modes) * args.repeats
        budget = config["budget"]
        print(f"Backend: {backend.name}; requested model: {backend.model}")
        print(f"{count} runs. EACH RUN: up to {budget['max_calls']} calls, {budget['max_seconds']} seconds,")
        print(f"{budget['max_tokens']:,} tokens and ${budget['max_estimated_usd']:.2f} accounting stop threshold.")
        print(f"Whole experiment accounting thresholds total: ${count * budget['max_estimated_usd']:.2f}.")
        print("Token and dollar thresholds are checked between waves; active calls can exceed them.")
        if args.command == "demo":
            print("SYNTHETIC DEMO: no model calls or charges. Counts and answers are scripted.")
        tag = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        output = args.out or Path("runs") / tag
        if output.exists():
            raise ValueError(f"Output already exists: {output}. Choose a new directory.")
        # Save after each mode, so a later provider error cannot lose previous runs.
        output.mkdir(parents=True, exist_ok=False)
        data = asyncio.run(experiment(task, config, backend, modes, args.repeats,
            checkpoint=lambda current: save(current, output)))
        return 1 if any(r["status"] != "complete" for r in data["results"]) else 0
    except KeyboardInterrupt:
        print("\nCancelled. Active local CLI processes were stopped; provider billing can still apply.", file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

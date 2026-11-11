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
from .generate import generate
from .report import write_report
from .runner import MODES, experiment
from .task import load_task, public_prompt, solve


def parser():
    p = argparse.ArgumentParser(description="Compare agent collaboration structures in a classroom.")
    sub = p.add_subparsers(dest="command", required=True)
    for name, help_text in [("demo", "Run a free, clearly labeled synthetic demonstration."),
                            ("compare", "Run all four modes with a real CLI backend."),
                            ("run", "Run one collaboration mode with a real CLI backend.")]:
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--task", type=Path, default=ROOT / "tasks/science-fair-17.json")
        cmd.add_argument("--config", type=Path, default=ROOT / "configs/classroom.toml")
        cmd.add_argument("--out", type=Path)
        cmd.add_argument("--repeats", type=int, default=1)
        cmd.add_argument("--rounds", type=int, help="Override rounds per agent (leader adds coordination calls).")
        if name != "demo":
            cmd.add_argument("--backend", choices=["codex", "claude"], default="codex")
            cmd.add_argument("--model", help="Explicit model override. There is no automatic expensive fallback.")
        if name == "run":
            cmd.add_argument("--mode", choices=MODES, required=True)
    replay = sub.add_parser("replay", help="Build an HTML report from an existing experiment JSON file.")
    replay.add_argument("recording", type=Path)
    replay.add_argument("--out", type=Path, default=Path("runs/replay.html"))
    task = sub.add_parser("task", help="Print the public case file.")
    task.add_argument("--task", type=Path, default=ROOT / "tasks/science-fair-17.json")
    new = sub.add_parser("new-task", help="Generate another uniquely solvable case.")
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
            task = generate(args.seed)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
            print(f"Created {args.out}: {len(task['clues'])} clues, exactly one solution.")
            return 0
        task = load_task(args.task)
        if args.command == "task":
            print(public_prompt(task))
            return 0
        config = load_config(args.config)
        if args.rounds is not None:
            if args.rounds < 1:
                raise ValueError("--rounds must be positive.")
            config["rounds"] = args.rounds
        if args.repeats < 1:
            raise ValueError("--repeats must be positive.")
        if len(solve(task)) != 1:
            raise ValueError("Task must have exactly one solution.")
        modes = [args.mode] if args.command == "run" else list(MODES)
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

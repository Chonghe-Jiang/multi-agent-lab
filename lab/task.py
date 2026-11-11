"""Logic-grid constraints, exact solver, and deterministic scoring.

Entity positions are time slots. Every category is a permutation of the slots.
The solver runs only in the evaluator, never inside an agent call.
"""
import json
from collections import deque
from pathlib import Path


def load_task(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def relation(op, a, b, distance=1):
    if op == "same":
        return a == b
    if op == "different":
        return a != b
    if op == "before":
        return a < b
    if op == "offset":
        return b - a == distance
    if op == "adjacent":
        return abs(a - b) == distance
    raise ValueError(f"Unknown relation: {op}")


def solve(task, limit=2):
    """AC-3 plus smallest-domain search; stop after `limit` solutions."""
    n = len(task["slots"])
    domains = {v: set(range(n)) for vs in task["categories"].values() for v in vs}
    domains.update({v: {i} for i, v in enumerate(task["slots"])})
    edges = []
    for values in task["categories"].values():
        for i, a in enumerate(values):
            for b in values[i + 1:]:
                edges.append((a, b, "different", 1))
    edges += [(c["a"], c["b"], c["op"], c.get("distance", 1)) for c in task["clues"]]
    arcs, incoming = [], {v: [] for v in domains}
    for a, b, op, d in edges:
        for x, y, reverse in [(a, b, False), (b, a, True)]:
            idx = len(arcs)
            arcs.append((x, y, op, d, reverse))
            incoming[y].append(idx)

    def propagate(ds):
        queue = deque(range(len(arcs)))
        while queue:
            x, y, op, d, reverse = arcs[queue.popleft()]
            keep = {a for a in ds[x] if any(
                relation(op, b, a, d) if reverse else relation(op, a, b, d)
                for b in ds[y])}
            if keep != ds[x]:
                if not keep:
                    return False
                ds[x] = keep
                queue.extend(incoming[x])
        return True

    solutions = []

    def search(ds):
        if len(solutions) >= limit or not propagate(ds):
            return
        candidates = [v for v in ds if len(ds[v]) > 1]
        if not candidates:
            solutions.append({v: next(iter(vals)) for v, vals in ds.items()})
            return
        v = min(candidates, key=lambda k: len(ds[k]))
        for value in sorted(ds[v]):
            child = {k: set(vals) for k, vals in ds.items()}
            child[v] = {value}
            search(child)
            if len(solutions) >= limit:
                return

    search(domains)
    return solutions


def rows_from_solution(task, solution):
    return [{"slot": slot, **{cat: next(v for v in vals if solution[v] == i)
            for cat, vals in task["categories"].items()}}
            for i, slot in enumerate(task["slots"])]


def candidate_positions(task, answer):
    """Read supplied cells only; do not infer or repair missing values."""
    rows = answer.get("schedule", []) if isinstance(answer, dict) else []
    if not isinstance(rows, list):
        rows = []
    slots, cats = task["slots"], task["categories"]
    positions = {slot: i for i, slot in enumerate(slots)}
    for cat, values in cats.items():
        for value in values:
            occurrences = [r for r in rows if isinstance(r, dict) and r.get(cat) == value]
            if len(occurrences) != 1:
                continue
            slot = occurrences[0].get("slot")
            if not isinstance(slot, str) or slot not in slots:
                continue
            if sum(isinstance(r, dict) and r.get("slot") == slot for r in rows) == 1:
                positions[value] = slots.index(slot)
    valid = (len(rows) == len(slots) and
        all(isinstance(r, dict) and set(r) == {"slot", *cats} for r in rows) and
        len(positions) == len(slots) + sum(len(v) for v in cats.values()))
    return positions, valid


def check_candidate(task, answer):
    """Check explicit public clues and grid rules, without solving the task."""
    positions, valid = candidate_positions(task, answer)
    checks = []
    for clue in task["clues"]:
        a, b = positions.get(clue["a"]), positions.get(clue["b"])
        ok = a is not None and b is not None and relation(clue["op"], a, b, clue.get("distance", 1))
        checks.append({"id": clue["id"], "satisfied": ok})
    return {"structurally_valid": valid, "clues": checks,
            "satisfied_clues": sum(c["satisfied"] for c in checks),
            "violated_clue_ids": [c["id"] for c in checks if not c["satisfied"]],
            "fully_satisfied": valid and all(c["satisfied"] for c in checks)}


def evaluate(task, answer, solution):
    """Reference accuracy is available only to the post-run evaluator."""
    positions, valid = candidate_positions(task, answer)
    values = [v for group in task["categories"].values() for v in group]
    correct = sum(v in positions and positions[v] == solution[v] for v in values)
    checks = check_candidate(task, answer)
    return {"score": round(100 * correct / len(values), 2), "correct_cells": correct,
            "total_cells": len(values), "exact": correct == len(values) and valid,
            "structurally_valid": valid, "clues": checks["clues"],
            "satisfied_clues": checks["satisfied_clues"]}


def public_prompt(task):
    lines = [task["title"], task["story"],
        f"Reconstruct all {len(task['slots'])} visits. Each time slot has exactly one value from each category.",
        "Each category value appears exactly once. Earlier/later refer to time, not room names.",
        "All clues are true. Return the entire schedule, not only the equipment owner.",
        "Slots in chronological order: " + ", ".join(task["slots"])]
    lines += [f"{cat}: {', '.join(values)}" for cat, values in task["categories"].items()]
    lines += [f"{c['id']}: {c['text']}" for c in task["clues"]]
    return "\n".join(lines)

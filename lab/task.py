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


def evaluate(task, answer, solution):
    """Invalid or duplicate cells earn no credit. No LLM judge is used."""
    rows = answer.get("schedule", []) if isinstance(answer, dict) else []
    if not isinstance(rows, list):
        rows = []
    slots = task["slots"]
    cats = task["categories"]
    positions = {slot: i for i, slot in enumerate(slots)}
    correct = total = 0
    valid_positions = dict(positions)
    for cat, values in cats.items():
        for value in values:
            occurrences = [r for r in rows if isinstance(r, dict) and r.get(cat) == value]
            total += 1
            if len(occurrences) != 1:
                continue
            row = occurrences[0]
            slot = row.get("slot")
            if not isinstance(slot, str) or slot not in positions:
                continue
            if sum(isinstance(r, dict) and r.get("slot") == slot for r in rows) != 1:
                continue
            valid_positions[value] = positions[slot]
            correct += positions[slot] == solution[value]
    clue_checks = []
    for c in task["clues"]:
        a, b = valid_positions.get(c["a"]), valid_positions.get(c["b"])
        ok = a is not None and b is not None and relation(c["op"], a, b, c.get("distance", 1))
        clue_checks.append({"id": c["id"], "satisfied": ok})
    structurally_valid = (len(rows) == len(slots) and
        all(isinstance(r, dict) and set(r) == {"slot", *cats} for r in rows) and
        len(valid_positions) == len(slots) + total)
    return {"score": round(100 * correct / total, 2), "correct_cells": correct,
            "total_cells": total, "exact": correct == total and structurally_valid,
            "structurally_valid": structurally_valid, "clues": clue_checks,
            "satisfied_clues": sum(c["satisfied"] for c in clue_checks)}


def public_prompt(task):
    lines = [task["title"], task["story"],
        "Reconstruct all six visits. Each time slot has exactly one value from each category.",
        "Each category value appears exactly once. Earlier/later refer to time, not room names.",
        "All clues are true. Return the entire schedule, not only the equipment owner.",
        "Slots in chronological order: " + ", ".join(task["slots"])]
    lines += [f"{cat}: {', '.join(values)}" for cat, values in task["categories"].items()]
    lines += [f"{c['id']}: {c['text']}" for c in task["clues"]]
    return "\n".join(lines)

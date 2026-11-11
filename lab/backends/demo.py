"""Synthetic responses for a free tour, never evidence about real models."""
import asyncio
import json

from ..task import rows_from_solution, solve


class DemoBackend:
    name, model, version = "demo", "synthetic-fixture", "1"

    def __init__(self, task):
        self.rows = rows_from_solution(task, solve(task)[0])

    async def call(self, prompt, schema, context, timeout, dollars):
        await asyncio.sleep(0.015)
        rows = [dict(row) for row in self.rows]
        turn = context["round"]
        if turn < 3:
            category = ("equipment" if "equipment" in rows[0] else "project") if turn == 1 else "room"
            index = int(context["agent"][-1]) - 1 if context["agent"].startswith("worker") else 0
            index %= len(rows)
            other = (index + 1) % len(rows)
            rows[index][category], rows[other][category] = rows[other][category], rows[index][category]
        if turn == 0:
            rows = []
        answer = {"schedule": rows,
            "message": "SYNTHETIC EXAMPLE: inspect linked clues, compare visits, and check category uniqueness. "
                       "These scripted answers demonstrate the report, not model performance.",
            "assignments": ["Check time relations and adjacent visits.", "Check room and student links.",
                            "Check project and equipment links."] if context["agent"] == "leader" else []}
        return {"text": json.dumps(answer), "usage": {"input_tokens": len(prompt) // 4,
                "cached_input_tokens": 0, "output_tokens": len(json.dumps(answer)) // 4},
                "actual_models": [self.model], "provider_cost_usd": 0, "errors": [], "tool_events": []}

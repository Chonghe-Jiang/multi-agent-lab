"""Round barriers make visibility explicit and independent of response timing."""
import asyncio
import copy
from datetime import datetime, timezone
import json
import math
import time

from .backends.cli import extract_json
from .config import estimate_cost
from .schema import response_schema, validate_answer
from .task import evaluate, public_prompt, solve
from .selection import choose_answer
from .diagnostics import annotate_result

MODES = ("solo", "leader", "independent", "exchange")
ALL_MODES = (*MODES, "solo-budget")


def prompt_for(task, agent, round_number, own, visible, instruction, message_chars):
    content = public_prompt(task) + f"\n\nYou are {agent}. This is round {round_number}.\n"
    content += instruction + "\n"
    content += ("Use only this prompt. No tools, external sources, or extra agents are allowed.\n"
        "Return JSON with exactly schedule, message, and assignments.\n"
        f"schedule: rows with slot and these fields: {', '.join(task['categories'])}. Use exact names.\n"
        "message: a concise conclusion with clue IDs, uncertainties, and useful corrections.\n"
        f"Keep message within {message_chars} characters.\n"
        "assignments: up to three short worker instructions, or [] for a worker.\n"
        f"Submit exactly {len(task['slots'])} schedule rows, even when uncertain. Make your best supported candidate.\n"
        "State uncertainties in message. Only the initial leader planning call can use schedule=[].\n")
    if own:
        content += "\nYour previous response:\n" + json.dumps(own["answer"], ensure_ascii=False) + "\n"
    if visible:
        content += "\nMessages explicitly delivered to you:\n"
        for item in visible:
            content += json.dumps(item, ensure_ascii=False) + "\n"
    return content


class ModeRunner:
    def __init__(self, task, config, backend, mode, repeat=1, progress=print, saved_state=None, call_checkpoint=None):
        self.task, self.config, self.backend, self.mode = task, config, backend, mode
        self.repeat, self.progress = repeat, progress
        self.started = time.monotonic()
        self.records = []
        self.reason = None
        saved_state = saved_state or {}
        self.saved = {c["id"]: copy.deepcopy(c) for c in saved_state.get("calls", [])}
        self.elapsed_offset = saved_state.get("elapsed_seconds", 0)
        self.call_checkpoint = call_checkpoint

    def elapsed(self):
        return self.elapsed_offset + time.monotonic() - self.started

    def totals(self):
        uses = [r["usage"] for r in self.records if r.get("usage")]
        estimate = sum(r.get("estimated_usd", 0) for r in self.records)
        provider = [r["provider_cost_usd"] for r in self.records if r.get("provider_cost_usd") is not None]
        return {"calls": len(self.records), "input_tokens": sum(u["input_tokens"] for u in uses),
                "output_tokens": sum(u["output_tokens"] for u in uses),
                "cached_input_tokens": sum(u.get("cached_input_tokens", 0) for u in uses),
                "estimated_usd": estimate,
                "provider_reported_usd": sum(provider) if len(provider) == len(self.records) and provider else None,
                "usage_complete": all(r.get("usage") is not None for r in self.records)}

    def can_start(self, size):
        b, totals = self.config["budget"], self.totals()
        checks = [(totals["calls"] + size > b["max_calls"], "call ceiling reached before the next complete wave"),
            (self.elapsed() >= b["max_seconds"], "time ceiling reached"),
            (totals["input_tokens"] + totals["output_tokens"] >= b["max_tokens"], "token stop threshold reached"),
            (max(totals["estimated_usd"], totals["provider_reported_usd"] or 0) >= b["max_estimated_usd"], "cost stop threshold reached"),
            (not totals["usage_complete"], "missing usage: further calls stopped because accounting is unknown")]
        for stop, reason in checks:
            if stop:
                self.reason = reason
                return False
        return True

    def message(self, record, include_schedule=False):
        answer = record["answer"]
        message = {"from": record["agent"], "call_id": record["id"],
                   "message": answer["message"][:self.config["message_chars"]]}
        if include_schedule:
            message["schedule"] = answer["schedule"]
        return message

    def persist(self):
        if self.call_checkpoint:
            self.call_checkpoint({"calls": self.records, "elapsed_seconds": self.elapsed()})

    async def wave(self, specs):
        base = len(self.records)
        old = [self.saved.get(f"call-{base + i + 1:03d}") for i in range(len(specs))]
        for spec, cached in zip(specs, old):
            if cached:
                agent, turn, own, visible, instruction = spec
                expected = prompt_for(self.task, agent, turn, own, visible, instruction, self.config["message_chars"])
                if cached["prompt"] != expected:
                    raise ValueError("Saved call prompt differs from this run. Use a new output directory.")
        if any(c and c['status'] == 'running' for c in old):
            restored = []
            for cached in old:
                if cached:
                    if cached['status'] == 'running':
                        cached.update(status='error', error='Interrupted call: usage is unknown. No automatic retry.',
                                      end_seconds=self.elapsed())
                    self.records.append(cached)
                    restored.append(cached)
            self.reason = 'interrupted call with unknown usage; remaining wave was not launched'
            self.persist()
            return restored
        new_count = sum(c is None for c in old)
        prefix = self.records
        # Include already billed members of a partially saved wave in budget accounting.
        self.records = prefix + [c for c in old if c]
        allowed = not new_count or self.can_start(new_count)
        remaining_dollars = self.config['budget']['max_estimated_usd'] - self.totals()['estimated_usd']
        self.records = prefix
        if not allowed:
            self.records.extend(c for c in old if c)
            return []
        async def invoke(spec):
            cached = self.saved.get(f"call-{len(self.records) + 1:03d}")
            if cached:
                self.records.append(cached)
                return cached
            agent, round_number, own, visible, instruction = spec
            record = {"id": f"call-{len(self.records) + 1:03d}", "agent": agent,
                      "round": round_number, "start_seconds": self.elapsed(),
                      "visible_call_ids": [v["call_id"] for v in visible],
                      "own_call_id": own["id"] if own else None,
                      "answer": None, "usage": None, "provider_cost_usd": None,
                      "estimated_usd": 0, "status": "running"}
            record["prompt"] = prompt_for(self.task, agent, round_number, own, visible, instruction,
                                         self.config["message_chars"])
            self.records.append(record)
            self.persist()
            self.progress(f"[{self.mode} / repeat {self.repeat}] {record['id']} {agent}, round {round_number}")
            try:
                remaining = self.config["budget"]["max_seconds"] - self.elapsed()
                timeout = max(0.01, min(remaining, self.config["budget"]["call_timeout_seconds"]))
                parsed = await self.backend.call(record["prompt"], response_schema(self.task, planning=(agent == "leader" and round_number == 0)),
                    {"mode": self.mode, "agent": agent, "round": round_number, "repeat": self.repeat},
                    timeout, max(0.01, remaining_dollars / max(1, new_count)))
                record["actual_models"] = parsed.get("actual_models", [])
                record["diagnostics"] = parsed.get("diagnostics", [])
                usage = parsed.get("usage")
                if usage is not None:
                    for key in ["input_tokens", "output_tokens"]:
                        if type(usage.get(key)) is not int or usage[key] < 0:
                            raise ValueError("Invalid token usage from backend.")
                    cached = usage.get("cached_input_tokens", 0)
                    if type(cached) is not int or not 0 <= cached <= usage["input_tokens"]:
                        raise ValueError("Invalid cached token usage from backend.")
                    record["usage"] = usage
                    record["estimated_usd"] = estimate_cost(usage, self.config["accounting"])
                cost = parsed.get("provider_cost_usd")
                if isinstance(cost, (int, float)) and math.isfinite(cost) and cost >= 0:
                    record["provider_cost_usd"] = cost
                if parsed.get("errors"):
                    raise ValueError("; ".join(parsed["errors"]))
                if parsed.get("tool_events"):
                    raise ValueError("Unexpected tool event. This mode requires tool-free calls.")
                answer = extract_json(parsed.get("text") or "")
                validate_answer(answer, self.task, planning=(agent == "leader" and round_number == 0))
                answer["message"] = answer["message"][:self.config["message_chars"]]
                answer["assignments"] = [s[:self.config["message_chars"]] for s in answer["assignments"]]
                record["answer"], record["status"] = answer, "ok"
            except asyncio.TimeoutError:
                record["status"], record["error"] = "error", "Call timed out. Usage and billing can be incomplete."
            except Exception as exc:
                record["status"], record["error"] = "error", str(exc)[:1500]
            record["end_seconds"] = self.elapsed()
            self.persist()
            return record
        records = await asyncio.gather(*(invoke(spec) for spec in specs))
        if any(r["status"] != "ok" for r in records):
            self.reason = "backend or response error; no automatic retries"
        return records

    async def run(self):
        rounds = self.config.get("solo_budget_rounds", 12) if self.mode == "solo-budget" else self.config["rounds"]
        last, final, voters = {}, None, []
        if self.mode == "leader":
            initial = await self.wave([("leader", 0, None, [],
                "Plan the investigation. Put three distinct instructions in assignments, one per worker. "
                "Do not declare a final solution yet.")])
            leader = initial[0] if initial else None
            for turn in range(1, rounds + 1):
                if self.reason or not leader:
                    break
                assignments = leader["answer"]["assignments"]
                specs = []
                for i in range(3):
                    agent = f"worker-{i + 1}"
                    assigned = assignments[i] if i < len(assignments) else "Independently check the full puzzle and report contradictions."
                    specs.append((agent, turn, last.get(agent), [self.message(leader, True)],
                                  "Work on the leader's assignment: " + assigned))
                workers = await self.wave(specs)
                if self.reason:
                    break
                if not workers:
                    break
                last.update({r["agent"]: r for r in workers})
                synthesis = await self.wave([("leader", turn, leader,
                    [self.message(r, True) for r in workers],
                    "Compare worker reports against the clues. Submit a full schedule. "
                    "Assign three follow-up checks for the next round, if any.")])
                if self.reason or not synthesis:
                    break
                leader = synthesis[0]
                final, voters = leader["answer"], [leader["id"]]
        else:
            agents = ["solo"] if self.mode in ("solo", "solo-budget") else [f"worker-{i + 1}" for i in range(4)]
            for turn in range(1, rounds + 1):
                specs = []
                for agent in agents:
                    # All workers read the SAME previous-round snapshot before any new call runs.
                    visible = [self.message(r) for name, r in sorted(last.items()) if name != agent] if self.mode == "exchange" else []
                    specs.append((agent, turn, last.get(agent), visible,
                        "Solve the entire puzzle. Check your candidate against every clue. "
                        "Revise your previous answer when evidence supports a correction."))
                records = await self.wave(specs)
                if self.reason or not records:
                    break
                last = {r["agent"]: r for r in records}
                final, voters = choose_answer(records, self.task, self.config.get("selection", "plurality"))
        totals = self.totals()
        if not totals["usage_complete"] and not self.reason:
            self.reason = "missing usage: accounting is unknown"
        solutions = solve(self.task)
        if len(solutions) != 1:
            raise ValueError("The evaluator requires exactly one solution.")
        # Scoring occurs only after collaboration ends. Agents never receive scores or answer keys.
        for r in self.records:
            if r["answer"]:
                r["evaluation"] = evaluate(self.task, r["answer"], solutions[0])
        result = {"mode": self.mode, "repeat": self.repeat, "backend": self.backend.name,
                "requested_model": self.backend.model, "backend_version": self.backend.version,
                "status": "stopped" if self.reason else "complete", "stop_reason": self.reason,
                "elapsed_seconds": self.elapsed(), "totals": totals, "calls": self.records,
                "final_answer": final, "selected_call_ids": voters,
                "evaluation": evaluate(self.task, final or {}, solutions[0]),
                "selection": self.config.get("selection", "plurality") if self.mode in ("independent", "exchange") else "native"}
        return annotate_result(self.task, result, solutions[0])


async def experiment(task, config, backend, modes=MODES, repeats=1, progress=print, checkpoint=None):
    solutions = solve(task)
    if len(solutions) != 1:
        raise ValueError("Task must have exactly one solution before any model calls start.")
    results = []
    data = {"format_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "synthetic": backend.name == "demo", "task": task, "config": config, "results": results}
    for repeat in range(1, repeats + 1):
        # Rotate mode order across repeats to reduce consistent order effects.
        order = list(modes)
        shift = (repeat - 1) % len(order)
        for mode in order[shift:] + order[:shift]:
            result = await ModeRunner(task, config, backend, mode, repeat, progress).run()
            results.append(result)
            if checkpoint:
                checkpoint(data)
            progress(f"{mode}: {result['status']}, {result['evaluation']['score']}%, {result['totals']['calls']} calls")
    return data

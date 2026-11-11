import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import signal
import tempfile


def extract_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("The response must be a JSON object.")
    return value


def parse_codex(stdout):
    answer, usage, errors, models = None, None, [], set()
    forbidden, diagnostics = [], []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        kind = event.get("type", "")
        if kind == "turn.completed":
            usage = event.get("usage")
        if kind in {"error", "turn.failed"}:
            errors.append(str(event.get("message", event.get("error", "Codex failed."))))
        item = event.get("item", {})
        if kind == "item.completed" and item.get("type") == "agent_message":
            answer = item.get("text", "")
        if item.get("type") == "error":
            message = item.get("message", "Codex emitted an error item.")
            if message.startswith("Code Mode is unavailable because code-mode host is disabled."):
                diagnostics.append(message)
            else:
                errors.append(message)
        elif kind.startswith("item.") and item.get("type") not in {None, "agent_message", "reasoning", "plan_update"}:
            forbidden.append(item.get("type"))
        if event.get("model"):
            models.add(event["model"])
    return {"text": answer, "usage": usage, "provider_cost_usd": None,
            "actual_models": sorted(models), "errors": errors, "tool_events": sorted(set(forbidden)), "diagnostics": diagnostics}


def parse_claude(stdout):
    event = json.loads(stdout)
    if not isinstance(event, dict):
        raise ValueError("Expected one Claude Code JSON result object.")
    raw = event.get("usage")
    usage = None
    if raw is not None:
        # Cache writes are input tokens billed at a separate rate by Anthropic.
        usage = {"input_tokens": raw.get("input_tokens", 0) + raw.get("cache_read_input_tokens", 0)
                 + raw.get("cache_creation_input_tokens", 0),
                 "cached_input_tokens": raw.get("cache_read_input_tokens", 0),
                 "cache_creation_input_tokens": raw.get("cache_creation_input_tokens", 0),
                 "output_tokens": raw.get("output_tokens", 0)}
    text = event.get("structured_output")
    if isinstance(text, dict):
        text = json.dumps(text)
    else:
        text = event.get("result", "")
    return {"text": text, "usage": usage, "provider_cost_usd": event.get("total_cost_usd"),
            "actual_models": sorted(event.get("modelUsage", {})),
            "errors": [str(event.get("errors", event.get("result", "Claude Code failed.")))]
                      if event.get("is_error") else [], "tool_events": []}


def codex_command(model, schema):
    command = ["codex", "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
               "--skip-git-repo-check", "--sandbox", "read-only", "--json", "--model", model,
               "--output-schema", str(schema), "-c", 'web_search="disabled"',
               "-c", 'model_reasoning_effort="low"', "-c", "project_doc_max_bytes=0"]
    # No shell, app connectors, browser, memory, plugins, or internal agent delegation.
    for feature in ["shell_tool", "multi_agent", "apps", "plugins", "hooks", "memories",
                    "code_mode", "code_mode_host", "browser_use", "computer_use",
                    "image_generation", "view_image", "skill_search"]:
        command += ["--disable", feature]
    return command + ["-"]


def claude_command(model, schema, dollars):
    return ["claude", "--safe-mode", "--print", "--model", model,
            "--tools", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--setting-sources", "", "--no-session-persistence", "--output-format", "json",
            "--json-schema", json.dumps(schema), "--max-budget-usd", str(max(0.01, dollars)),
            "--system-prompt", "You solve classroom logic puzzles. Use only the supplied prompt. "
            "Return the requested JSON object. Do not call tools or delegate."]


async def stop_process(proc):
    if proc.returncode is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except ProcessLookupError:
        pass
    await proc.wait()


class CLIBackend:
    def __init__(self, name, model):
        self.name, self.model = name, model
        if not shutil.which(name):
            raise ValueError(f"{name} is not installed. See docs/backends.md, or use 'python -m lab demo'.")
        version = __import__("subprocess").run([name, "--version"], capture_output=True, text=True, timeout=10)
        self.version = version.stdout.strip()

    async def call(self, prompt, schema, context, timeout, dollars):
        with tempfile.TemporaryDirectory(prefix="agent-lab-") as tmp:
            schema_path = Path(tmp) / "response-schema.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = codex_command(self.model, schema_path) if self.name == "codex" else claude_command(self.model, schema, dollars)
            env = dict(os.environ)
            # This controller owns collaboration. Prevent an inherited nested CC session flag.
            env.pop("CLAUDECODE", None)
            env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
            proc = await asyncio.create_subprocess_exec(*command, cwd=tmp, env=env,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, start_new_session=(os.name == "posix"))
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                await stop_process(proc)
                raise
            try:
                parsed = (parse_codex if self.name == "codex" else parse_claude)(stdout.decode())
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(f"Cannot parse {self.name} output (exit {proc.returncode}). {exc}") from exc
            if proc.returncode and not parsed["errors"]:
                parsed["errors"] = [f"{self.name} exited with code {proc.returncode}. Run its login command and check model access."]
            return parsed

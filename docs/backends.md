# Backend setup

Use one backend for your first comparison. Model differences can obscure communication effects.

The lab requires recent CLIs. Older releases can lack isolation flags. Unsupported flags produce a stopped run, with no automatic fallback.

## Codex

Install Codex from the [official CLI instructions](https://developers.openai.com/codex/cli/).

```bash
codex --version
codex login
python -m lab run --backend codex --mode solo --rounds 1
```

`codex exec` reuses CLI authentication. API automation can use `CODEX_API_KEY` for the invoking process.

The default model is `gpt-6-luna`, subject to account availability. The lab requests low reasoning effort.

The adapter uses `--ignore-user-config`, `--ignore-rules`, `--ephemeral`, and a fresh temporary directory.

Ignoring user configuration also excludes custom provider routes. Use the standard Codex authentication path for this first version.

Shell tools, web search, plugins, app connectors, memory, and internal multi-agent delegation are disabled.

Each call requests a structured JSON response. JSONL events supply token usage. Unexpected tool events invalidate the call.

Some Codex event versions do not report an actual model ID. The report then says “not reported.”

Sources: [Non-interactive mode](https://developers.openai.com/codex/noninteractive), [model availability](https://developers.openai.com/codex/models), [configuration reference](https://developers.openai.com/codex/config-reference).

## Claude Code

Install Claude Code from the [official setup instructions](https://code.claude.com/docs/en/setup).

```bash
claude --version
claude auth login
python -m lab run --backend claude --mode solo --rounds 1
```

The default model alias is `haiku`. For a fixed experiment, use the full model ID available to your account.

The adapter uses `--safe-mode`, an empty built-in tool list, an empty MCP configuration, and no session persistence.

Safe mode preserves normal authentication. The adapter does not use bare mode, which changes authentication behavior.

Each call uses a temporary directory, a custom system prompt, and a JSON response schema.

The remaining accounting allowance is divided across the wave and passed as each call's `--max-budget-usd` value.

That provider control also uses estimates. It is not a strict bank-level spending limit.

Claude reports input tokens, cache reads, cache writes, output tokens, and usually an estimated dollar cost.

The lab includes cache reads and writes in total input tokens. Cache-write accounting uses the configured input rate.

Sources: [Programmatic use](https://code.claude.com/docs/en/headless), [CLI reference](https://code.claude.com/docs/en/cli-reference), [model configuration](https://code.claude.com/docs/en/model-config).

## Errors and troubleshooting

- If a model is unavailable, use `--model` with an available model ID.
- If authentication fails, run the backend login command outside the lab.
- If flags are unsupported, update the CLI.
- If a call times out, inspect the saved error and increase the per-call timeout in your configuration.
- If token usage is missing, further calls stop. The report marks usage as unknown.

The controller does not retry failures automatically. Failed requests can still consume usage.

Each live report includes the CLI version. Managed account policies can still affect model access and behavior.

Local process-tree cancellation supports Linux and macOS. For Windows, use WSL for the same cancellation behavior.

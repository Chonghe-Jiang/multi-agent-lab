# Multi-Agent Lab

A hands-on lab for high school students. Give AI agents the same difficult case, change how they communicate, and measure the result.

**The question:** Does collaboration improve answers enough to justify its extra time and cost?

The lab uses Codex or Claude Code as a backend. The orchestration code is small, readable Python with no runtime dependencies.

## Try it for free

Requirements: Git and Python 3.11 or later.

```bash
git clone https://github.com/Chonghe-Jiang/multi-agent-lab.git
cd multi-agent-lab
python -m lab demo
```

Open the printed `report.html` path in your browser. The report works offline.

The demo uses **scripted responses**, not real model calls. Its answers, token counts, and timings cannot establish a winning mode.

You can also open [the example report](examples/report.html) or rebuild it:

```bash
python -m lab replay examples/demo.json --out runs/replay.html
```

On some systems, use `python3` instead of `python`.

## Run real agents

Install and authenticate **one** backend. See [backend setup](docs/backends.md).

```bash
python -m lab doctor

# Start with one agent and one round.
python -m lab run --backend codex --mode solo --rounds 1

# Compare all four modes.
python -m lab compare --backend codex

# Use Claude Code instead.
python -m lab compare --backend claude
```

Real runs use your account or API credentials. They consume paid usage or subscription allowances.

Defaults select `gpt-6-luna` for Codex and `haiku` for Claude Code. Availability depends on your account and CLI version.

The lab never requests a more expensive fallback. Use an explicit model override when necessary:

```bash
python -m lab compare --backend codex --model YOUR_AVAILABLE_MODEL
```

Every run records the requested model, reported model IDs, CLI version, task, and configuration.

## Four ways to work

| Mode | Agents | Each round | Final answer |
| --- | --- | --- | --- |
| `solo` | One | Solve, then revise its own answer | Last answer |
| `leader` | One leader and three workers | Workers receive assignments. The leader reviews their responses. | Last leader synthesis |
| `independent` | Four workers | Each worker sees only its own previous response | Plurality over whole schedules |
| `exchange` | Four workers | Each worker also receives three peer messages from the previous round | Same plurality rule |

For tied votes, the lowest worker ID wins. Voting never uses the answer key or evaluation scores.

Workers run in parallel within a round. A barrier separates rounds, so faster responses cannot change message visibility.

Each call starts a fresh conversation. The controller supplies the task, the previous response, and explicitly permitted messages.

Independent workers cannot read peer files, sessions, or results. Tools and built-in delegation are disabled in both backends.

Exchange workers share their short `message` fields, not entire schedules or private reasoning. The leader receives worker messages and schedules.

## The challenge

Six students visited a science fair at six different times. Each visit has a room, project, and equipment item.

Recover **all 24 category assignments** from 30 linked clues. A correct equipment-owner guess alone does not earn full credit.

Three cases are included. An exact constraint solver checks that each case has exactly one solution.

```bash
python -m lab task
python -m lab compare --backend codex --task tasks/science-fair-29.json
python -m lab new-task --seed 81 --out tasks/my-case.json
```

The evaluator scores each correct cell. Duplicate values or duplicate time rows lose credit. An exact solution also requires a valid complete schedule.

Agents receive the same public clues. The solver runs outside agent calls. Agents never receive answer keys, intermediate scores, or automatic correctness feedback.

Difficulty is structural, not a measured model success rate. Pilot the cases before classroom use.

## A longer, configurable budget

The default configuration allows three rounds per worker.

| Ceiling or threshold | Classroom default, per mode | Extended, per mode |
| --- | --- | --- |
| Calls | 16 | 24 |
| Wall time | 15 minutes | 30 minutes |
| Tokens, including cache reads | 240,000 | 480,000 |
| Accounting estimate | $3 | $6 |
| Rounds | 3 | 5 |
| Shared message length | 1,600 characters | 2,400 characters |

A default comparison uses up to four separate budgets. Its accounting thresholds total **$12**. The extended comparison totals **$24**.

**These dollar figures are stop thresholds, not guaranteed spending caps.** The supplied accounting rates are assumptions, not provider prices.

Update the rates in `configs/classroom.toml` for your exact model and provider. Subscription usage is not equivalent to an API bill.

Token and dollar thresholds are checked between waves. Already active calls can exceed them. A timeout also cannot reverse provider charges.

Call ceilings apply before each whole wave. Wall-time limits stop local CLI processes. Missing usage stops further calls.

```bash
python -m lab compare --backend codex --config configs/extended.toml
```

Equal ceilings do not mean equal spending. With three rounds, solo makes 3 calls, independent/exchange make 12, and leader makes 13.

For an additional baseline, give solo more revision calls under the same ceilings:

```bash
python -m lab run --backend codex --mode solo --rounds 12
```

The report includes actual calls and resource use. Compare quality against those measurements, not agent count alone.

## Read the report

The standalone HTML report contains:

- Per-run scores, exact solutions, token counts, time, and cost accounting.
- A quality-versus-tokens plot.
- A timeline of overlapping calls.
- Each worker response and leader assignment.
- The exact prompt and permitted source-call IDs for each call.
- Errors, unknown usage, and budget stops.

Solver calls must submit a complete candidate, even when uncertain. Only the initial leader plan can omit its schedule.

`experiment.json` contains the same data for your own analysis. Reports save after each completed mode.

If a later run fails, earlier results remain available. An interrupted current mode is not saved.

## Classroom experiment

1. Write a prediction before the first real run.
2. Keep the model, task, and configuration fixed across modes.
3. Compare the four modes on one case.
4. Identify an answer that improved or worsened after a message.
5. Repeat with another case and several trials.
6. Plot answer quality against actual tokens or cost.
7. Explain the limits of your evidence.

For repeated trials:

```bash
python -m lab compare --backend codex --repeats 5
```

Five trials mean twenty separate mode budgets. The CLI prints the total accounting thresholds before the first call.

Mode order rotates across repeats. Repeats do not set a provider random seed or guarantee statistically independent outputs.

This lab compares **collaboration protocols**, not different third-party framework libraries. Read [the experiment design](docs/experiment-design.md) before drawing conclusions.

## Explore the code

```text
lab/
  backends/       Codex, Claude Code, and synthetic adapters
  runner.py       Protocols, round barriers, budgets, and visibility
  task.py         Exact solver and deterministic evaluation
  generate.py     Reproducible case generator
  report.html     Offline report interface
configs/          Editable budgets and accounting rates
tasks/            Public cases, without stored answer keys
examples/         Synthetic recording and report
tests/            Protocol, accounting, adapter, and evaluation tests
```

Run the checks:

```bash
python -m unittest discover -s tests -v
```

Optional editable installation:

```bash
python -m pip install -e .
agent-lab demo
```

Keep the checkout when you use the editable installation. Tasks and configuration files remain in the checkout.

## License

MIT. See [LICENSE](LICENSE).

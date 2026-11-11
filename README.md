# Multi-Agent Lab

A classroom lab for high school students. Give AI agents the same case, change how they communicate, and measure the result.

The lab uses Codex or Claude Code as a backend. Its Python orchestration code has no runtime dependencies.

## Start with the free demo

Requirements: Git and Python 3.11 or later.

```bash
git clone https://github.com/Chonghe-Jiang/multi-agent-lab.git
cd multi-agent-lab
python -m lab demo
```

Open the printed `report.html` path. The report works offline.

The demo uses **scripted responses**, not real model calls. Its scores, timings, and token counts are examples.

On some systems, use `python3` instead of `python`.

## Choose a case

```bash
python -m lab list
python -m lab list --difficulty medium
python -m lab task --task tasks/science-fair-easy-201.json
```

The [active catalog](tasks/README.md) has **3 easy, 4 medium, and 3 hard cases**.

| Structural level | Visits | Categories | Cells to recover |
| --- | --- | --- | --- |
| Easy | 4 | 3 | 12 |
| Medium | 5 | 4 | 20 |
| Hard | 6 | 4 | 24 |

Each case has exactly one solution. Easy cases use direct links. Medium and hard cases require longer combinations of clues.

**Levels describe structure, not calibrated model success rates.** Pilot the cases with your chosen model before classroom use.

The default case is easy-201. All ten original six-person cases remain available by file path for historical comparisons.

## Run real agents

Install and authenticate one backend. See [backend setup](docs/backends.md).

```bash
python -m lab doctor

# One real call on the default easy case.
python -m lab run --backend codex --mode solo --rounds 1

# Compare five modes on one case.
python -m lab compare --backend codex

# Use Claude Code instead.
python -m lab compare --backend claude
```

Real calls use your account or API credentials. They consume paid usage or subscription allowances.

Defaults request `gpt-6-luna` for Codex and `haiku` for Claude Code. Model access depends on your account and CLI version.

The lab requests no expensive fallback. Use `--model YOUR_AVAILABLE_MODEL` for an explicit override.

## Compare collaboration and computation

| Mode | Agents | Context and final submission |
| --- | --- | --- |
| `solo` | One | Three rounds of self-revision. Submit its last answer. |
| `solo-budget` | One | Twelve rounds under the same resource ceilings. Submit its last answer. |
| `leader` | One leader and three workers | The leader assigns work, receives worker candidates, and submits a synthesis. |
| `independent` | Four workers | Each worker sees only its own previous response. Select a final candidate deterministically. |
| `exchange` | Four workers | Each worker also sees three peer messages from the previous round. Use the same final selector. |

Workers run in parallel within a round. A barrier separates rounds, so response timing cannot change visibility.

Every call starts a fresh conversation. The controller supplies the public task, its own previous response, and permitted messages.

Tools and built-in delegation are disabled. Independent workers cannot inspect peer files or sessions.

Exchange workers share short messages. The leader receives worker messages and complete candidate schedules.

With three rounds, call counts are 3, 12, 13, 12, and 12 for solo, solo-budget, leader, independent, and exchange.

```bash
# Keep the original four-mode experiment.
python -m lab compare --backend codex --modes solo leader independent exchange

# Change the longer single-agent baseline.
python -m lab compare --backend codex --solo-rounds 10
```

Equal ceilings do not force equal spending. The report plots actual tokens against answer quality, including complete-round trajectories.

## Select final candidates with public clues

`public-checker` is the default selector for independent and exchange modes.

It ranks existing candidates by grid validity, satisfied public clues, and whole-schedule vote count. Agent ID breaks remaining ties.

The checker reads the supplied candidate and public clues. It does not solve missing cells or use the reference answer.

`plurality` preserves the original whole-schedule voting baseline. Agent ID breaks tied votes.

```bash
python -m lab compare --backend codex --selection plurality
```

Solo and leader modes retain their native last submission. The selector does not replace them with a better worker or earlier response.

Agents receive no checker feedback. Reference accuracy and best-worker comparisons appear only after the run.

## Run or resume a full suite

Start with a free suite:

```bash
python -m lab suite --backend demo --out runs/demo-suite
python -m lab suite --resume --out runs/demo-suite
```

Run real agents across the catalog:

```bash
python -m lab suite --backend codex --out runs/live-suite

# Continue with the saved tasks, configuration, backend, and modes.
python -m lab suite --resume --out runs/live-suite
```

Optional controls:

```bash
python -m lab suite --backend codex --difficulty easy \
  --modes solo independent exchange --repeats 3 \
  --parallel-cases 2 --out runs/easy-study
```

The suite saves a journal before each model call and after its response. Resume reuses saved responses and keeps terminal mode results.

If a saved call has an unknown outcome, resume marks that mode as stopped. It does not retry a potentially billed call.

Other modes continue. Use a new output directory for an intentional fresh trial.

Resume checks the task content, configuration, model, CLI version, and source-code digest. Changed experiments require a new directory.

Only one suite controller can hold an output directory. The operating system releases its lock after a process exits.

The suite writes `index.html`, `summary.csv`, `summary.json`, per-case reports, and a configuration/source manifest.

Each case uses the same mode budgets. More cases and repeats multiply total usage. The CLI prints planned accounting thresholds before calls.

## Compare selectors without new model calls

```bash
python -m lab reselect runs/live-suite \
  --selection public-checker --out runs/live-suite-reselected
```

A single `experiment.json` file also works. Original recordings remain unchanged.

Reselection changes only the final independent/exchange candidate choice. It reuses the same agent responses and original resource measurements.

Reports show before/after scores and label the operation as **offline reselection**. This is not a fresh multi-agent experiment.

## Budgets and accounting

| Ceiling or stop threshold | Classroom, per mode | Extended, per mode |
| --- | --- | --- |
| Calls | 16 | 24 |
| Wall time | 15 minutes | 30 minutes |
| Tokens, including cache reads | 240,000 | 480,000 |
| Accounting estimate | $3 | $6 |
| Regular rounds / solo-budget rounds | 3 / 12 | 5 / 20 |
| Shared message length | 1,600 characters | 2,400 characters |

A default five-mode comparison has accounting thresholds totaling **$15**. A ten-case suite totals **$150**, before repeats.

These figures are stop thresholds, not guaranteed spending caps. Supplied rates are accounting assumptions, not verified provider prices.

Update the configuration for your exact model and provider. Subscription allowances are not equivalent to API dollar charges.

Token and dollar thresholds apply between waves. Active calls can exceed them. Local cancellation cannot reverse provider charges.

Call ceilings apply before each whole wave. Missing usage stops further calls. Reports keep unknown usage separate from zero usage.

```bash
python -m lab compare --backend codex --config configs/extended.toml
```

## Read the diagnostics

Each report includes final scores, known resource use, exact prompts, message visibility, and a work timeline.

Additional diagnostics show:

- The selected answer and the best final worker score.
- Correct worker answers lost during selection.
- Whole-schedule vote ties.
- Revisions that improved, worsened, or preserved accuracy.
- Score-versus-token curves across complete rounds.
- Offline selection comparisons, when applicable.

Best-worker scores use the reference answer after the run. They diagnose lost opportunities and never select an answer during a run.

## Classroom investigations

1. Write a prediction before the first real run.
2. Keep the task and model fixed across modes.
3. Compare actual resource use with quality.
4. Inspect a correction and a harmful revision.
5. Compare plurality with public-checker using the same recording.
6. Repeat across cases and trials.

These cases share one task structure. Results do not automatically transfer to coding, research, or planning tasks.

Read [the experiment design](docs/experiment-design.md) for comparison limits and [suite recovery](docs/suite-recovery.md) for checkpoint behavior.

## Develop

```bash
python -m unittest discover -s tests -v
python -m lab new-task --difficulty medium --seed 81 --out tasks/my-case.json
```

Optional editable installation:

```bash
python -m pip install -e .
agent-lab demo
```

Keep the checkout for its task and configuration files. The MIT license is in [LICENSE](LICENSE).

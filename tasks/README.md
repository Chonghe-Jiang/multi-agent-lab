# Case catalog

The lab includes ten science-fair mysteries. Each case has six visits, four categories, and 30 clues.

Each case has a different complete schedule and clue set. All ten cases have exactly one solution.

These cases vary one puzzle structure. They are not ten different task types or calibrated difficulty levels.

| Case | Seed | Task file |
| --- | --- | --- |
| 01 | 17 | [science-fair-17.json](science-fair-17.json) |
| 02 | 29 | [science-fair-29.json](science-fair-29.json) |
| 03 | 43 | [science-fair-43.json](science-fair-43.json) |
| 04 | 59 | [science-fair-59.json](science-fair-59.json) |
| 05 | 71 | [science-fair-71.json](science-fair-71.json) |
| 06 | 83 | [science-fair-83.json](science-fair-83.json) |
| 07 | 97 | [science-fair-97.json](science-fair-97.json) |
| 08 | 109 | [science-fair-109.json](science-fair-109.json) |
| 09 | 127 | [science-fair-127.json](science-fair-127.json) |
| 10 | 149 | [science-fair-149.json](science-fair-149.json) |

## Select a case

Print a case without model calls:

```bash
python -m lab task --task tasks/science-fair-149.json
```

Run a free synthetic demonstration:

```bash
python -m lab demo --task tasks/science-fair-149.json
```

Compare real agents on the selected case:

```bash
python -m lab compare --backend codex --task tasks/science-fair-149.json
```

Each comparison uses four separate mode budgets. Ten comparisons use forty mode budgets, before repeats.

For a study, compare all four modes on each case. Keep the model and configuration fixed across cases.

The solver checks uniqueness and grading without paid model calls. Model success rates still require real trials.

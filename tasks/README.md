# Classroom case catalog

The active catalog contains ten cases: three easy, four medium, and three hard.

Each case has exactly one solution. The levels describe structure, not measured model success rates.

| Case | Level | Visits / categories | File |
| --- | --- | --- | --- |
| 01 | Easy | 4 / 3 | [science-fair-easy-201.json](science-fair-easy-201.json) |
| 02 | Easy | 4 / 3 | [science-fair-easy-211.json](science-fair-easy-211.json) |
| 03 | Easy | 4 / 3 | [science-fair-easy-223.json](science-fair-easy-223.json) |
| 04 | Medium | 5 / 4 | [science-fair-medium-307.json](science-fair-medium-307.json) |
| 05 | Medium | 5 / 4 | [science-fair-medium-311.json](science-fair-medium-311.json) |
| 06 | Medium | 5 / 4 | [science-fair-medium-313.json](science-fair-medium-313.json) |
| 07 | Medium | 5 / 4 | [science-fair-medium-317.json](science-fair-medium-317.json) |
| 08 | Hard | 6 / 4 | [science-fair-17.json](science-fair-17.json) |
| 09 | Hard | 6 / 4 | [science-fair-29.json](science-fair-29.json) |
| 10 | Hard | 6 / 4 | [science-fair-43.json](science-fair-43.json) |

Easy cases contain direct time and category links. Medium cases combine relationships across five visits.

Hard cases retain the original six-person puzzles. Difficulty needs live calibration with the chosen model.

The machine-readable list is [catalog.json](catalog.json).

```bash
python -m lab list
python -m lab demo --task tasks/science-fair-medium-307.json
python -m lab suite --backend demo --difficulty easy --out runs/easy-demo
```

## Legacy cases

All ten original six-person files remain available. Seeds are 17, 29, 43, 59, 71, 83, 97, 109, 127, and 149.

Three appear in the active catalog. The other seven support historical replay and direct comparisons by file path.

```bash
python -m lab compare --backend codex --task tasks/science-fair-149.json
```

A default active suite contains fifty mode runs, including the longer solo baseline. Cases and repeats each multiply usage.

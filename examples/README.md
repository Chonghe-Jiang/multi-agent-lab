# Example recording

`demo.json` and `report.html` contain a synthetic demonstration. No model generated these responses.

All modes use the same scripted correction pattern. The example cannot support conclusions about real model performance.

Open `report.html` in a browser, or rebuild it:

```bash
python -m lab replay examples/demo.json --out runs/replay.html
```

For a real recording, run `python -m lab compare --backend codex` with your authenticated CLI.

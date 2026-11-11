"""A standalone report with no server, external scripts, or network requests."""
import json
from pathlib import Path


def write_report(data, path):
    payload = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = Path(__file__).with_name("report.html").read_text(encoding="utf-8")
    Path(path).write_text(template.replace("__EXPERIMENT_DATA__", payload), encoding="utf-8")

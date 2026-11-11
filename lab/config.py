from pathlib import Path
import math
import tomllib

ROOT = Path(__file__).resolve().parent.parent


def load_config(path):
    with Path(path).open("rb") as handle:
        config = tomllib.load(handle)
    for section, keys in {
        "budget": ["max_calls", "max_seconds", "call_timeout_seconds", "max_tokens", "max_estimated_usd"],
        "accounting": ["input_per_million", "cached_input_per_million", "output_per_million"],
    }.items():
        for key in keys:
            value = config.get(section, {}).get(key)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{section}.{key} must be a positive finite number.")
    for key in ["rounds", "message_chars"]:
        if type(config.get(key)) is not int or config[key] < 1:
            raise ValueError(f"{key} must be a positive integer.")
    if type(config["budget"]["max_calls"]) is not int or type(config["budget"]["max_tokens"]) is not int:
        raise ValueError("max_calls and max_tokens must be integers.")
    for name in ["codex", "claude"]:
        if not isinstance(config.get("models", {}).get(name), str) or not config["models"][name].strip():
            raise ValueError(f"models.{name} must name a model.")
    if config.get("selection", "plurality") not in ("plurality", "public-checker"):
        raise ValueError("selection must be plurality or public-checker.")
    if type(config.get("solo_budget_rounds", 12)) is not int or config.get("solo_budget_rounds", 12) < 1:
        raise ValueError("solo_budget_rounds must be a positive integer.")
    return config


def estimate_cost(usage, accounting):
    cached = min(usage.get("cached_input_tokens", 0), usage["input_tokens"])
    # Cache writes use the input accounting rate; exact provider billing can differ.
    return ((usage["input_tokens"] - cached) * accounting["input_per_million"]
            + cached * accounting["cached_input_per_million"]
            + usage["output_tokens"] * accounting["output_per_million"]) / 1_000_000

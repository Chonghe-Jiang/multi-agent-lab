"""One response contract for all roles, providers, and modes."""


def response_schema(task, planning=False):
    row = {"slot": {"type": "string", "enum": task["slots"]}}
    row.update({k: {"type": "string", "enum": v} for k, v in task["categories"].items()})
    return {"type": "object", "additionalProperties": False,
            "properties": {
                "schedule": {"type": "array", "minItems": 0 if planning else len(task["slots"]),
                    "maxItems": len(task["slots"]), "items": {"type": "object", "properties": row,
                    "required": list(row), "additionalProperties": False}},
                "message": {"type": "string"},
                "assignments": {"type": "array", "items": {"type": "string"}}},
            "required": ["schedule", "message", "assignments"]}


def validate_answer(value, task, planning=False):
    if set(value) != {"schedule", "message", "assignments"}:
        raise ValueError("Response needs exactly schedule, message, and assignments.")
    if not isinstance(value["message"], str):
        raise ValueError("message must be a string.")
    if not isinstance(value["assignments"], list) or not all(isinstance(s, str) for s in value["assignments"]):
        raise ValueError("assignments must be a list of strings.")
    if len(value["assignments"]) > 3:
        raise ValueError("At most three worker assignments are allowed.")
    if not isinstance(value["schedule"], list) or len(value["schedule"]) > len(task["slots"]):
        raise ValueError("schedule must be a list of at most six rows.")
    if not planning and len(value["schedule"]) != len(task["slots"]):
        raise ValueError("A solver response must submit exactly six schedule rows.")
    allowed = {"slot": task["slots"], **task["categories"]}
    for row in value["schedule"]:
        if not isinstance(row, dict) or set(row) != set(allowed):
            raise ValueError("Each schedule row needs a slot and all category fields.")
        for field, choices in allowed.items():
            if not isinstance(row[field], str) or row[field] not in choices:
                raise ValueError(f"Unknown {field} value.")

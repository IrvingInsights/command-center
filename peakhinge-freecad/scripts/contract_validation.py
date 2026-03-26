"""Lightweight validators for Step-1 edit contracts.

Purposefully minimal to avoid extra dependencies.
"""


def _require_fields(data: dict, required: list[str]) -> list[str]:
    missing = [field for field in required if field not in data]
    return [f"Missing required field: {field}" for field in missing]


def validate_edit_request(payload: dict) -> list[str]:
    errors = _require_fields(payload, ["request_text", "subassembly", "timestamp_utc"])

    if payload.get("subassembly") != "pipe_pivot":
        errors.append("subassembly must be 'pipe_pivot' for Step-1")

    request_text = payload.get("request_text")
    if not isinstance(request_text, str) or not request_text.strip():
        errors.append("request_text must be a non-empty string")

    timestamp_utc = payload.get("timestamp_utc")
    if not isinstance(timestamp_utc, str) or "T" not in timestamp_utc:
        errors.append("timestamp_utc must be an ISO-like datetime string")

    user_id = payload.get("user_id")
    if user_id is not None and not isinstance(user_id, str):
        errors.append("user_id must be a string when provided")

    return errors


def validate_edit_plan(payload: dict) -> list[str]:
    errors = _require_fields(payload, ["subassembly", "changes", "assumptions", "status"])

    if payload.get("subassembly") != "pipe_pivot":
        errors.append("subassembly must be 'pipe_pivot' for Step-1")

    status = payload.get("status")
    if status not in {"applied", "failed"}:
        errors.append("status must be 'applied' or 'failed'")

    assumptions = payload.get("assumptions")
    if not isinstance(assumptions, list) or any(not isinstance(x, str) for x in assumptions):
        errors.append("assumptions must be a list of strings")

    changes = payload.get("changes")
    if not isinstance(changes, list):
        errors.append("changes must be a list")
    elif status == "applied" and len(changes) < 1:
        errors.append("changes must contain at least one item when status is 'applied'")
    else:
        for idx, change in enumerate(changes):
            if not isinstance(change, dict):
                errors.append(f"changes[{idx}] must be an object")
                continue
            missing = [k for k in ["parameter", "old_value", "new_value", "unit"] if k not in change]
            for field in missing:
                errors.append(f"changes[{idx}] missing field: {field}")

    return errors


def assert_valid_edit_request(payload: dict) -> None:
    errors = validate_edit_request(payload)
    if errors:
        raise ValueError("Invalid edit request: " + "; ".join(errors))


def assert_valid_edit_plan(payload: dict) -> None:
    errors = validate_edit_plan(payload)
    if errors:
        raise ValueError("Invalid edit plan: " + "; ".join(errors))

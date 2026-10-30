"""Content revisions keep unrelated profile changes out of body edit conflicts."""

import hashlib
import json


def body_revision(measurements: dict | None) -> str:
    # JSONB may normalize numbers (175.0 -> 175). Hash their normalized representation.
    def normalize(value):
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value

    data = json.dumps(normalize(measurements or {}), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()

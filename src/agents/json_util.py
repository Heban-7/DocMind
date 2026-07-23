"""Small shared helpers for agent JSON parsing."""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from model output (tolerates markdown fences)."""
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_OBJECT_RE.search(text)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}

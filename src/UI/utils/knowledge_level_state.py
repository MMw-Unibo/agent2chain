"""Knowledge-level state helpers shared by UI server modules."""

from __future__ import annotations

from typing import Any

KNOWLEDGE_LEVEL_STATE_KEY = "knowledge_level"
VALID_LEVELS = {1, 2, 3}
DEFAULT_LEVEL = 1


def normalize_level(value: Any) -> int:
    if isinstance(value, int) and value in VALID_LEVELS:
        return value
    return DEFAULT_LEVEL


def extract_knowledge_level(value: Any) -> int | None:
    if isinstance(value, dict):
        candidate = value.get("knowledgeLevel")
        if isinstance(candidate, int) and candidate in VALID_LEVELS:
            return candidate
        for nested in value.values():
            extracted = extract_knowledge_level(nested)
            if extracted is not None:
                return extracted
        return None

    if isinstance(value, list):
        for item in value:
            extracted = extract_knowledge_level(item)
            if extracted is not None:
                return extracted
        return None

    return None


def append_knowledge_level_marker(reply: str, level: int | None) -> str:
    if level is None:
        return reply

    normalized_level = normalize_level(level)
    marker = f"__KNOWLEDGE_LEVEL__{normalized_level}"
    return f"{reply}\n{marker}" if reply else marker

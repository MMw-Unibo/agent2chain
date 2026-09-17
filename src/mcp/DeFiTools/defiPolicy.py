from __future__ import annotations


BEGINNER_LEVEL = 1
MIN_LEVEL_FOR_STATE_CHANGING_DEFI = 2


def normalize_knowledge_level(value: int | str) -> int:
	if isinstance(value, bool):
		raise ValueError("knowledgeLevel must be 1, 2, or 3")

	if isinstance(value, int):
		if value in {1, 2, 3}:
			return value
		raise ValueError("knowledgeLevel must be 1, 2, or 3")

	raw = str(value or "").strip().lower()
	aliases = {
		"1": 1,
		"level 1": 1,
		"beginner": 1,
		"novice": 1,
		"2": 2,
		"level 2": 2,
		"intermediate": 2,
		"3": 3,
		"level 3": 3,
		"expert": 3,
		"advanced": 3,
	}

	if raw in aliases:
		return aliases[raw]

	raise ValueError("knowledgeLevel must be one of: 1, 2, 3, Beginner, Intermediate, Expert")


def enforce_state_changing_defi_knowledge(operation: str, knowledge_level: int | str) -> dict | None:
	try:
		normalized_level = normalize_knowledge_level(knowledge_level)
	except ValueError as error:
		return {
			"error": f"{operation} error: Invalid knowledgeLevel: {error}",
			"source": "defi",
		}

	if normalized_level < MIN_LEVEL_FOR_STATE_CHANGING_DEFI:
		return {
			"error": (
				f"{operation} error: DeFi state-changing operations are disabled for Beginner users "
				"(knowledgeLevel=1)."
			),
			"knowledgeLevel": normalized_level,
			"requiredMinimumLevel": MIN_LEVEL_FOR_STATE_CHANGING_DEFI,
			"source": "defi",
		}

	return None
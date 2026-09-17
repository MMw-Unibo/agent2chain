"""BlockchainAgent plugins."""

from .activity_logger_plugin import ActivityLoggerPlugin

__all__ = ["LlmAsAJudge", "ActivityLoggerPlugin"]


def __getattr__(name: str):
	if name == "LlmAsAJudge":
		from .agent_as_a_judge import LlmAsAJudge

		return LlmAsAJudge
	if name == "ActivityLoggerPlugin":
		return ActivityLoggerPlugin
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

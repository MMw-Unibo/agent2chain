"""Helper functions related to the system."""

import os
from pathlib import Path

DEBUG_MODE_INSTRUCTIONS = """
    This is really important! If the agent or user asks you to be verbose or if debug_mode is True, do the following:
      1. If this is the the start of a new task, explain who you are, what you are going to do, what tools you use, and what agents you delegate to.
      2. During the task, provide regular status updates on what you are doing, what you have done so far, and what you plan to do next.
      3. If you are delegating to another agent, ask the agent or tool to also be verbose.
      4. If at any point in the task you send or receive data, show the data in a clear, formatted way. Do not summarize it in english. Simple format the JSON objects.
      5. Step 4 is so important that I'm going to repeat it:
        a. If at any point in the task you create, send or receive data, show the data in a clear, formatted way. Do not summarize it in english. Simple format the JSON objects.
"""


def load_src_env() -> None:
  """Load environment variables from src/.env if present."""
  src_dir = Path(__file__).resolve().parents[1]
  env_path = src_dir / ".env"
  if not env_path.exists():
    return

  for raw_line in env_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
      continue

    key, value = line.split("=", 1)
    key = key.strip()
    if key.startswith("export "):
      key = key.removeprefix("export ").strip()
    value = value.strip().strip('"').strip("'")
    if not key:
      continue

    if value:
      os.environ[key] = value
    else:
      os.environ.setdefault(key, value)
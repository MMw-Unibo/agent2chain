#!/bin/bash

# A script to automate the execution of Agent2Chain.
# It starts all necessary components in the background,
# and then runs the agent with the custom Python UI.

# Exit immediately if any command exits with a non-zero status.
set -e

# The UI server entrypoint.
UI_SERVER="src/UI/server.py"

# Log directory used by runtime components.
LOG_DIRS=(".logs")

if [ ! -f "$UI_SERVER" ]; then
  echo "Error: UI server '$UI_SERVER' not found."
  echo "Please run this script from the root of the repository."
  exit 1
fi

# Load environment variables
if [ -f src/.env ]; then
  set -a
  source src/.env
  set +a
fi

# Set up and activate a virtual environment.
echo "Setting up the Python virtual environment..."

if [ ! -d ".venv" ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv
  else
    if command -v python3 >/dev/null 2>&1; then
      python3 -m venv .venv
    else
      python -m venv .venv
    fi
  fi
fi

# Detect the correct activation script path across Windows and Unix-like shells.
if [ -f ".venv/Scripts/activate" ]; then
  source .venv/Scripts/activate
elif [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
else
  echo "Error: no virtual environment activation script found in .venv."
  exit 1
fi

if [ -x ".venv/Scripts/python.exe" ]; then
  VENV_PYTHON=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
  VENV_PYTHON=".venv/bin/python"
else
  echo "Error: no Python executable found in .venv."
  exit 1
fi

echo "Virtual environment activated."

if command -v uv >/dev/null 2>&1; then
  echo "Using uv to manage dependencies (project install handled by uv sync)."
else
  echo "Installing project in editable mode..."
  "$VENV_PYTHON" -m ensurepip --upgrade >/dev/null 2>&1 || true
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -e .
fi

# Create directories for log files.
for log_dir in "${LOG_DIRS[@]}"; do
  mkdir -p "$log_dir"
done

# Cleanup function for background processes
cleanup() {
  echo ""
  echo "Shutting down background processes..."
  if [ ${#pids[@]} -ne 0 ]; then
    kill "${pids[@]}" 2>/dev/null
    wait "${pids[@]}" 2>/dev/null
  fi
  echo "Cleanup complete."
}

trap cleanup EXIT

# Explicitly sync when uv is available.
if command -v uv >/dev/null 2>&1; then
  echo "Syncing virtual environment with uv sync..."
  if uv sync; then
    echo "Virtual environment synced successfully."
  else
    echo "uv sync failed, attempting to recover with a clean virtual environment..."
    deactivate 2>/dev/null || true
    chmod -R u+w .venv 2>/dev/null || true
    rm -rf .venv
    uv venv

    if [ -f ".venv/Scripts/activate" ]; then
      source .venv/Scripts/activate
    elif [ -f ".venv/bin/activate" ]; then
      source .venv/bin/activate
    else
      echo "Error: no virtual environment activation script found after recovery."
      exit 1
    fi

    if uv sync; then
      echo "Virtual environment recovered and synced successfully."
    else
      echo "Error: uv sync failed after recovery. Aborting deployment."
      exit 1
    fi
  fi
else
  echo "uv not found, skipping uv sync."
fi

# Clear old logs.
echo "Clearing the logs directory..."
for log_dir in "${LOG_DIRS[@]}"; do
  if [ -d "$log_dir" ]; then
    rm -f "$log_dir"/*
  fi
done

# Start all the agents & server.
pids=()

echo ""

echo "Starting the Blockchain Agent UI..."
if command -v uv >/dev/null 2>&1; then
  UV_RUN_CMD="uv run --no-sync"
  if [ -f "src/.env" ]; then
    UV_RUN_CMD="$UV_RUN_CMD --env-file src/.env"
  fi
  $UV_RUN_CMD python "$UI_SERVER"
else
  "$VENV_PYTHON" "$UI_SERVER"
fi

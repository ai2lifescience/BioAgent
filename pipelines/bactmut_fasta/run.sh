#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${1:?Usage: run.sh config.runtime.yaml}"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Configuration file not found: $CONFIG_PATH" >&2
  exit 2
fi

config_value() {
  python3 - "$CONFIG_PATH" "$1" <<'PY'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as stream:
    value = yaml.safe_load(stream)
for part in sys.argv[2].split("."):
    if not isinstance(value, dict) or part not in value:
        raise SystemExit(f"Missing configuration key: {sys.argv[2]}")
    value = value[part]
if value is None:
    raise SystemExit(f"Configuration key is null: {sys.argv[2]}")
print(value)
PY
}

PIPELINE_LABEL="$(config_value label)"
export PIPELINE_LABEL
python3 "$SCRIPT_DIR/workflow.py" "$CONFIG_PATH"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${1:?runtime config path is required}"

PIPELINE_ENV="bacfunc"
PIPELINE_MODULE="bacfunc"

config_value() {
  local key="$1"
  local fallback="${2:-}"
  python - "$CONFIG_PATH" "$key" "$fallback" <<'PY'
import sys
import yaml

config_path, key, fallback = sys.argv[1:4]
with open(config_path, encoding="utf-8") as handle:
    config = yaml.safe_load(handle) or {}
value = config.get(key, fallback)
if value is None:
    value = fallback
print(value)
PY
}

input_path="$(config_value input_path)"
output_dir="$(config_value output_dir)"
input_type="$(config_value input_type auto)"
analysis_mode="$(config_value analysis_mode auto)"
threads="$(config_value threads 8)"
sample_id="$(config_value sample_id)"

if [[ -z "$input_path" || ! -e "$input_path" ]]; then
  printf 'Input path does not exist: %s\n' "$input_path" >&2
  exit 2
fi

if [[ -z "$output_dir" ]]; then
  printf 'Missing output_dir in runtime config: %s\n' "$CONFIG_PATH" >&2
  exit 2
fi

mkdir -p "$output_dir"

command=(
  conda run -n "$PIPELINE_ENV"
  python -m "$PIPELINE_MODULE" run
  --config "$SCRIPT_DIR/config.yaml"
  --input-type "$input_type"
  --analysis-mode "$analysis_mode"
  --output "$output_dir"
  --threads "$threads"
)

if [[ -d "$input_path" ]]; then
  command+=(--input-dir "$input_path")
else
  command+=(--input "$input_path")
fi

if [[ -n "$sample_id" ]]; then
  command+=(--sample-id "$sample_id")
fi

exec "${command[@]}"

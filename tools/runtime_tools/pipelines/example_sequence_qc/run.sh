#!/usr/bin/env bash
set -euo pipefail
config_path="${1:?Usage: bash run.sh CONFIG_YAML}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${script_dir}/workflow.py" "${config_path}"

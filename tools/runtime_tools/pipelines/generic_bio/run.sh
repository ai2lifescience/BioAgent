#!/usr/bin/env bash
set -euo pipefail

config_path="${1:?config path is required}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "${script_dir}/workflow.py" "${config_path}"

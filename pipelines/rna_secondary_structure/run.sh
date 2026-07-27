#!/usr/bin/env bash
set -euo pipefail

config_path="${1:?runtime config path is required}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec python "${script_dir}/workflow.py" "${config_path}"

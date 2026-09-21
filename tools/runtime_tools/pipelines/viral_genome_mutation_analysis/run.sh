#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="$1"

export VIRUS_DB="${VIRUS_DB:-/hpcdisk1/jcyj_group/jiangxq226/pathdect_pipeline/database/pcf/virus_db_reference_merged3/reference.fasta}"
export VIRUS_METADATA="${VIRUS_METADATA:-/hpcdisk1/jcyj_group/jiangxq226/pathdect_pipeline/database/pcf/virus_db_reference_merged3/meta.tsv}"

python "$SCRIPT_DIR/workflow.py" "$CONFIG_PATH"

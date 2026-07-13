#!/usr/bin/env bash
set -euo pipefail

config_path="${1:?config path is required}"

config_value() {
    local dotted_path="$1"
    local default_value="${2:-}"
    python - "${config_path}" "${dotted_path}" "${default_value}" <<'PY'
import sys
import yaml

config_path, dotted_path, default_value = sys.argv[1:4]
with open(config_path, "r", encoding="utf-8") as handle:
    config = yaml.safe_load(handle) or {}

value = config
for part in dotted_path.split("."):
    if not isinstance(value, dict) or part not in value:
        value = default_value
        break
    value = value[part]

if isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print(default_value)
else:
    print(value)
PY
}

input_path="$(config_value input_path)"
output_dir="$(config_value output_dir)"
report_path="$(config_value report_path)"
metrics_path="$(config_value metrics_path)"
normalized_path="$(config_value normalized_path)"
label="$(config_value label generic_shell)"
normalize_mode="$(config_value params.normalize_mode whitespace)"
uppercase="$(config_value params.uppercase false)"

if [[ -z "${input_path}" ]]; then
    printf 'config missing input_path: %s\n' "${config_path}" >&2
    exit 2
fi
if [[ -z "${report_path}" ]]; then
    printf 'config missing report_path: %s\n' "${config_path}" >&2
    exit 2
fi
if [[ -z "${metrics_path}" ]]; then
    printf 'config missing metrics_path: %s\n' "${config_path}" >&2
    exit 2
fi
if [[ -z "${normalized_path}" ]]; then
    printf 'config missing normalized_path: %s\n' "${config_path}" >&2
    exit 2
fi
if [[ -z "${label}" ]]; then
    label="shell"
fi
if [[ -z "${output_dir}" ]]; then
    output_dir="$(dirname "${report_path}")"
fi
if [[ -z "${normalize_mode}" ]]; then
    normalize_mode="whitespace"
fi
if [[ -z "${uppercase}" ]]; then
    uppercase="false"
fi

mkdir -p "${output_dir}"
mkdir -p "$(dirname "${normalized_path}")"
mkdir -p "$(dirname "${metrics_path}")"
mkdir -p "$(dirname "${report_path}")"

case "${normalize_mode}" in
    whitespace)
        tr -s '[:space:]' ' ' < "${input_path}" > "${normalized_path}"
        ;;
    lines)
        sed '/^[[:space:]]*$/d' "${input_path}" > "${normalized_path}"
        ;;
    raw)
        cp "${input_path}" "${normalized_path}"
        ;;
    *)
        printf 'unsupported normalize_mode: %s\n' "${normalize_mode}" >&2
        exit 2
        ;;
esac

if [[ "${uppercase}" == "true" ]]; then
    tmp_path="${normalized_path}.tmp"
    tr '[:lower:]' '[:upper:]' < "${normalized_path}" > "${tmp_path}"
    mv "${tmp_path}" "${normalized_path}"
fi

line_count="$(wc -l < "${input_path}" | tr -d ' ')"
word_count="$(wc -w < "${input_path}" | tr -d ' ')"
char_count="$(wc -c < "${input_path}" | tr -d ' ')"

cat > "${metrics_path}" <<JSON
{
  "status": "ok",
  "pipeline": "shell",
  "label": "${label}",
  "normalize_mode": "${normalize_mode}",
  "uppercase": ${uppercase},
  "line_count": ${line_count},
  "word_count": ${word_count},
  "char_count": ${char_count}
}
JSON

cat > "${report_path}" <<EOF
# Shell Pipeline Report

- Label: ${label}
- Config: ${config_path}
- Input: ${input_path}
- Normalize mode: ${normalize_mode}
- Uppercase: ${uppercase}
- Lines: ${line_count}
- Words: ${word_count}
- Characters: ${char_count}
- Normalized text: ${normalized_path}
EOF

printf 'Shell pipeline completed: %s\n' "${report_path}"

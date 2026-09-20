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
metadata_path="$(config_value metadata_path)"
output_dir="$(config_value output_dir)"
report_path="$(config_value report_path)"
metrics_path="$(config_value metrics_path)"
normalized_path="$(config_value normalized_path)"
subtype_path="$(config_value subtype_path)"
label="$(config_value label generic_shell)"
normalize_mode="$(config_value params.normalize_mode whitespace)"
uppercase="$(config_value params.uppercase false)"
sequence_id_column="$(config_value params.sequence_id_column sequence_id)"
subtype_column="$(config_value params.subtype_column subtype)"
missing_subtype="$(config_value params.missing_subtype unassigned)"

if [[ -z "${input_path}" ]]; then
    printf 'config missing input_path: %s\n' "${config_path}" >&2
    exit 2
fi
if [[ -z "${metadata_path}" ]]; then
    printf 'config missing metadata_path: %s\n' "${config_path}" >&2
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
if [[ -z "${subtype_path}" ]]; then
    printf 'config missing subtype_path: %s\n' "${config_path}" >&2
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
mkdir -p "$(dirname "${subtype_path}")"

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

assignment_counts="$(
    python - \
        "${input_path}" \
        "${metadata_path}" \
        "${subtype_path}" \
        "${sequence_id_column}" \
        "${subtype_column}" \
        "${missing_subtype}" <<'PY'
import csv
import sys
from collections import Counter
from pathlib import Path


sequence_path = Path(sys.argv[1])
metadata_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])
sequence_id_column = sys.argv[4]
subtype_column = sys.argv[5]
missing_subtype = sys.argv[6]


def sequence_ids(path: Path) -> list[str]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    nonempty = [line for line in lines if line]
    if nonempty and nonempty[0].startswith(">"):
        identifiers = [
            line[1:].split()[0] for line in nonempty if line.startswith(">") and line[1:].strip()
        ]
    elif nonempty and nonempty[0].startswith("@"):
        if len(nonempty) % 4:
            raise SystemExit(f"invalid FASTQ record structure in {path}")
        identifiers = []
        for index in range(0, len(nonempty), 4):
            header = nonempty[index]
            if not header.startswith("@") or not header[1:].strip():
                raise SystemExit(f"invalid FASTQ header at record {index // 4 + 1} in {path}")
            identifiers.append(header[1:].split()[0])
    else:
        identifiers = [line.split()[0] for line in nonempty]
    duplicates = sorted(identifier for identifier, count in Counter(identifiers).items() if count > 1)
    if duplicates:
        raise SystemExit(f"duplicate sequence ID(s): {', '.join(duplicates)}")
    if not identifiers:
        raise SystemExit(f"no sequence IDs found in {path}")
    return identifiers


def subtype_by_id(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        first_line = handle.readline()
        handle.seek(0)
        delimiter = "\t" if "\t" in first_line else ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        columns = reader.fieldnames or []
        missing_columns = [
            column for column in (sequence_id_column, subtype_column) if column not in columns
        ]
        if missing_columns:
            raise SystemExit(
                f"metadata missing column(s) {', '.join(missing_columns)}; "
                f"available columns: {', '.join(columns)}"
            )
        values: dict[str, str] = {}
        for row_number, row in enumerate(reader, start=2):
            identifier = (row.get(sequence_id_column) or "").strip()
            if not identifier:
                continue
            if identifier in values:
                raise SystemExit(f"duplicate metadata ID '{identifier}' at row {row_number}")
            values[identifier] = (row.get(subtype_column) or "").strip()
        return values


identifiers = sequence_ids(sequence_path)
subtypes = subtype_by_id(metadata_path)
assigned = 0
with output_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
    writer.writerow(["sequence_id", "subtype"])
    for identifier in identifiers:
        subtype = subtypes.get(identifier) or missing_subtype
        assigned += int(identifier in subtypes and bool(subtypes[identifier]))
        writer.writerow([identifier, subtype])

print(len(identifiers), assigned, len(identifiers) - assigned)
PY
)"
read -r sequence_count assigned_subtype_count unassigned_subtype_count <<< "${assignment_counts}"

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
  "char_count": ${char_count},
  "sequence_count": ${sequence_count},
  "assigned_subtype_count": ${assigned_subtype_count},
  "unassigned_subtype_count": ${unassigned_subtype_count}
}
JSON

cat > "${report_path}" <<EOF
# Shell Pipeline Report

- Label: ${label}
- Config: ${config_path}
- Input: ${input_path}
- Metadata: ${metadata_path}
- Normalize mode: ${normalize_mode}
- Uppercase: ${uppercase}
- Lines: ${line_count}
- Words: ${word_count}
- Characters: ${char_count}
- Sequences: ${sequence_count}
- Assigned subtypes: ${assigned_subtype_count}
- Unassigned subtypes: ${unassigned_subtype_count}
- Normalized text: ${normalized_path}
- Subtype assignments: ${subtype_path}
EOF

printf 'Shell pipeline completed: %s\n' "${report_path}"

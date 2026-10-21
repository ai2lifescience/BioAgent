version 1.0

# StrobeTaxa k-mer/strobemer classification for clean reads.
# db_dir is a shared bind-mounted directory to avoid localizing a large nested DB.
workflow StrobeTaxaDetection {
  input {
    String sample_id
    File   clean_r1
    File?  clean_r2
    String db_dir

    Float feat3_threshold = 0.5
    Int   bp_per_block     = 1000000
    Boolean memmap         = true

    String docker_image = "cncb/strobe-taxa:v1.0"
    Int cpu              = 8
    Int memory_gb        = 64
    Int disk_gb          = 200
  }

  call ClassifyReads {
    input:
      sample_id                = sample_id,
      clean_r1                 = clean_r1,
      clean_r2                 = clean_r2,
      db_dir                   = db_dir,
      threads                  = cpu,
      feat3_threshold          = feat3_threshold,
      bp_per_block             = bp_per_block,
      memmap                   = memmap,
      docker_image             = docker_image,
      cpu                      = cpu,
      memory_gb                = memory_gb,
      disk_gb                  = disk_gb
  }

  output {
    File classified_tsv = ClassifyReads.classified_tsv
    File report_tsv     = ClassifyReads.report_tsv
    File signature_coverage_csv = ClassifyReads.signature_coverage_csv
  }
}

task ClassifyReads {
  input {
    String sample_id
    File   clean_r1
    File?  clean_r2
    String db_dir
    Int    threads
    Float  feat3_threshold
    Int    bp_per_block
    Boolean memmap
    String docker_image
    Int    cpu
    Int    memory_gb
    Int    disk_gb
  }

  command <<<
    set -euo pipefail

    DB="~{db_dir}"
    if [ ! -d "$DB" ]; then
      echo "StrobeTaxa database directory is not visible in the container: $DB" >&2
      echo "Mount its parent path in cromwell.conf (the provided config mounts /data)." >&2
      exit 2
    fi

    python3 -m strobe_taxa.cli check-db --db "$DB" --target "index,signature"

    R2="~{if defined(clean_r2) then select_first([clean_r2]) else ''}"
    PREP_ARGS=(--r1 "~{clean_r1}" --output combined.fastq)
    if [ -n "$R2" ]; then
      PREP_ARGS+=(--r2 "$R2")
    fi
    python3 /app/scripts/prepare_reads.py "${PREP_ARGS[@]}"

    MEMMAP_OPT="--no-memmap"
    if [ "~{memmap}" = "true" ]; then
      MEMMAP_OPT="--memmap"
    fi

    python3 -m strobe_taxa.cli classify \
      --reads combined.fastq \
      --db "$DB" \
      --output "~{sample_id}.classified.tsv" \
      --report-out "~{sample_id}.report.tsv" \
      --threads ~{threads} \
      --feat3-threshold ~{feat3_threshold} \
      --bp-per-block ~{bp_per_block} \
      --no-progress \
      "$MEMMAP_OPT" \
      --signature-coverage-out "~{sample_id}.signature_coverage.csv"
  >>>

  output {
    File classified_tsv = "~{sample_id}.classified.tsv"
    File report_tsv     = "~{sample_id}.report.tsv"
    File signature_coverage_csv = "~{sample_id}.signature_coverage.csv"
  }

  runtime {
    docker: docker_image
    cpu: cpu
    memory: "~{memory_gb} GB"
    disks: "local-disk ~{disk_gb} SSD"
  }
}

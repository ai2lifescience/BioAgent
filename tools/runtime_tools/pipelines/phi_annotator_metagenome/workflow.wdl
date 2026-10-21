version 1.0

## PHI-base 宏基因组注释（reads，不组装）
##
## FASTQ -> DIAMOND blastx。可选 R2 只作为第二条 FASTQ 一起检索，不做 PE 配对。
## 全部运行参数在 input 中，不读取 config.yaml。
## 数据库以 String 路径传入，由运行环境挂载，Cromwell 不本地化。

workflow PhiAnnotatorMetagenome {
  input {
    String sample_id
    File   fastq_r1
    File?  fastq_r2

    String diamond_db
    String metadata
    String db_version = "PHI-base 5.6"

    Int threads = 8
    Int min_read_length = 0

    Float min_identity = 80.0
    Float min_query_coverage = 0.0
    Float min_subject_coverage = 0.0
    Float max_evalue = 0.00001
    Int   max_target_seqs = 25
    Int   min_alignment_length = 30

    String diamond_executable = "diamond"
    String diamond_blastx_options = ""

    Array[String] metadata_fields = [
      "subject_id=subject_id",
      "phi_id=phi_id",
      "gene_name=gene_name",
      "pathogen=pathogen",
      "host=host",
      "host_group=host_group",
      "phenotype=phenotype",
      "interaction_type=interaction_type",
      "function=function",
      "evidence=evidence",
      "reference=reference"
    ]

    String pipeline_dir = "/opt/phi-annotator-v2"
    String docker_image = "cncb/phi-annotator:v1.0"
    Int    memory_gb = 32
    Int    disk_gb = 200
  }

  call RunPhiMetagenome {
    input:
      sample_id               = sample_id,
      fastq_r1                = fastq_r1,
      fastq_r2                = fastq_r2,
      diamond_db              = diamond_db,
      metadata                = metadata,
      db_version              = db_version,
      threads                 = threads,
      min_read_length         = min_read_length,
      min_identity            = min_identity,
      min_query_coverage      = min_query_coverage,
      min_subject_coverage    = min_subject_coverage,
      max_evalue              = max_evalue,
      max_target_seqs         = max_target_seqs,
      min_alignment_length    = min_alignment_length,
      diamond_executable      = diamond_executable,
      diamond_blastx_options  = diamond_blastx_options,
      metadata_fields         = metadata_fields,
      pipeline_dir            = pipeline_dir,
      docker_image            = docker_image,
      memory_gb               = memory_gb,
      disk_gb                 = disk_gb
  }

  output {
    File hits      = RunPhiMetagenome.hits
    File read_hits = RunPhiMetagenome.read_hits
    File summary   = RunPhiMetagenome.summary
    File qc        = RunPhiMetagenome.qc
    File status    = RunPhiMetagenome.status
    File manifest  = RunPhiMetagenome.manifest
    File report    = RunPhiMetagenome.report
    String sample  = sample_id
  }
}

task RunPhiMetagenome {
  input {
    String sample_id
    File   fastq_r1
    File?  fastq_r2

    String diamond_db
    String metadata
    String db_version

    Int threads
    Int min_read_length

    Float min_identity
    Float min_query_coverage
    Float min_subject_coverage
    Float max_evalue
    Int   max_target_seqs
    Int   min_alignment_length

    String diamond_executable
    String diamond_blastx_options
    Array[String] metadata_fields

    String pipeline_dir
    String docker_image
    Int    memory_gb
    Int    disk_gb
  }

  command <<<
    set -euo pipefail

    INPUT_DIR="$PWD/wdl_reads"
    mkdir -p "$INPUT_DIR"
    ln -s "~{fastq_r1}" "$INPUT_DIR/$(basename "~{fastq_r1}")"
    if [[ -n "~{fastq_r2}" && -f "~{fastq_r2}" ]]; then
      ln -s "~{fastq_r2}" "$INPUT_DIR/$(basename "~{fastq_r2}")"
    fi

    OUT_DIR="$PWD/phi_out"
    mkdir -p "$OUT_DIR"

    EXTRA_ARGS=()
    if [[ -n "~{diamond_blastx_options}" ]]; then
      EXTRA_ARGS+=(--diamond-blastx-options="~{diamond_blastx_options}")
    fi

    python "~{pipeline_dir}/workflow.py" run \
      --input "$INPUT_DIR" \
      --output "$OUT_DIR" \
      --sample-id "~{sample_id}" \
      --input-type reads \
      --threads ~{threads} \
      --min-read-length ~{min_read_length} \
      --diamond-db "~{diamond_db}" \
      --metadata "~{metadata}" \
      --db-version "~{db_version}" \
      --diamond-executable "~{diamond_executable}" \
      --min-identity ~{min_identity} \
      --min-query-coverage ~{min_query_coverage} \
      --min-subject-coverage ~{min_subject_coverage} \
      --max-evalue ~{max_evalue} \
      --max-target-seqs ~{max_target_seqs} \
      --min-alignment-length ~{min_alignment_length} \
      --metadata-field ~{sep=" --metadata-field " metadata_fields} \
      "${EXTRA_ARGS[@]}"
  >>>

  output {
    File hits      = "phi_out/phi_hits.tsv"
    File read_hits = "phi_out/phi_read_hits.tsv"
    File summary   = "phi_out/phi_summary.tsv"
    File qc        = "phi_out/qc.json"
    File status    = "phi_out/status.json"
    File manifest  = "phi_out/manifest.json"
    File report    = "phi_out/report.md"
  }

  runtime {
    docker: docker_image
    cpu:    threads
    memory: memory_gb + " GB"
    disks:  "local-disk " + disk_gb + " SSD"
  }
}

version 1.0

## PHI-base 全基因组 / 蛋白注释
##
## 二选一：
##   genome_fasta  -> input_type=nucleic, Prodigal 预测 ORF 后 DIAMOND blastp
##   protein_fasta -> input_type=protein, 直接 DIAMOND blastp
## 全部运行参数在 input 中，不读取 config.yaml。
## 数据库以 String 路径传入，由运行环境挂载，Cromwell 不本地化。

workflow PhiAnnotatorGenome {
  input {
    String sample_id
    File?  genome_fasta
    File?  protein_fasta

    String diamond_db
    String metadata
    String db_version = "PHI-base 5.6"

    Int    threads = 8
    String genome_context = "complete"
    Int    min_contig_length = 0

    Float min_identity = 30.0
    Float min_query_coverage = 50.0
    Float min_subject_coverage = 0.0
    Float max_evalue = 0.00001
    Int   max_target_seqs = 25
    Int   min_alignment_length = 0

    String diamond_executable = "diamond"
    String diamond_options = "--sensitive"
    String prodigal_executable = "prodigal"
    String prodigal_options = ""

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
    Int    disk_gb = 100
  }

  call RunPhiGenome {
    input:
      sample_id            = sample_id,
      genome_fasta         = genome_fasta,
      protein_fasta        = protein_fasta,
      diamond_db           = diamond_db,
      metadata             = metadata,
      db_version           = db_version,
      threads              = threads,
      genome_context       = genome_context,
      min_contig_length    = min_contig_length,
      min_identity         = min_identity,
      min_query_coverage   = min_query_coverage,
      min_subject_coverage = min_subject_coverage,
      max_evalue           = max_evalue,
      max_target_seqs      = max_target_seqs,
      min_alignment_length = min_alignment_length,
      diamond_executable   = diamond_executable,
      diamond_options      = diamond_options,
      prodigal_executable  = prodigal_executable,
      prodigal_options     = prodigal_options,
      metadata_fields      = metadata_fields,
      pipeline_dir         = pipeline_dir,
      docker_image         = docker_image,
      memory_gb            = memory_gb,
      disk_gb              = disk_gb
  }

  output {
    File hits     = RunPhiGenome.hits
    File summary  = RunPhiGenome.summary
    File qc       = RunPhiGenome.qc
    File status   = RunPhiGenome.status
    File manifest = RunPhiGenome.manifest
    File report   = RunPhiGenome.report
    String sample = sample_id
  }
}

task RunPhiGenome {
  input {
    String sample_id
    File?  genome_fasta
    File?  protein_fasta

    String diamond_db
    String metadata
    String db_version

    Int    threads
    String genome_context
    Int    min_contig_length

    Float min_identity
    Float min_query_coverage
    Float min_subject_coverage
    Float max_evalue
    Int   max_target_seqs
    Int   min_alignment_length

    String diamond_executable
    String diamond_options
    String prodigal_executable
    String prodigal_options
    Array[String] metadata_fields

    String pipeline_dir
    String docker_image
    Int    memory_gb
    Int    disk_gb
  }

  command <<<
    set -euo pipefail

    GENOME="~{default="" genome_fasta}"
    PROTEIN="~{default="" protein_fasta}"
    if [[ -n "$GENOME" && -f "$GENOME" && -n "$PROTEIN" && -f "$PROTEIN" ]]; then
      echo "Provide either genome_fasta or protein_fasta, not both." >&2
      exit 1
    fi
    if [[ -n "$GENOME" && -f "$GENOME" ]]; then
      INPUT="$GENOME"
      INPUT_TYPE="nucleic"
    elif [[ -n "$PROTEIN" && -f "$PROTEIN" ]]; then
      INPUT="$PROTEIN"
      INPUT_TYPE="protein"
    else
      echo "genome_fasta or protein_fasta is required." >&2
      exit 1
    fi

    OUT_DIR="$PWD/phi_out"
    mkdir -p "$OUT_DIR"

    EXTRA_ARGS=()
    if [[ "$INPUT_TYPE" == "nucleic" ]]; then
      EXTRA_ARGS+=(--genome-context "~{genome_context}" --min-contig-length ~{min_contig_length})
    fi
    if [[ -n "~{diamond_options}" ]]; then
      EXTRA_ARGS+=(--diamond-options="~{diamond_options}")
    fi
    if [[ -n "~{prodigal_options}" ]]; then
      EXTRA_ARGS+=(--prodigal-options="~{prodigal_options}")
    fi

    python "~{pipeline_dir}/workflow.py" run \
      --input "$INPUT" \
      --output "$OUT_DIR" \
      --sample-id "~{sample_id}" \
      --input-type "$INPUT_TYPE" \
      --threads ~{threads} \
      --diamond-db "~{diamond_db}" \
      --metadata "~{metadata}" \
      --db-version "~{db_version}" \
      --diamond-executable "~{diamond_executable}" \
      --prodigal-executable "~{prodigal_executable}" \
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
    File hits     = "phi_out/phi_hits.tsv"
    File summary  = "phi_out/phi_summary.tsv"
    File qc       = "phi_out/qc.json"
    File status   = "phi_out/status.json"
    File manifest = "phi_out/manifest.json"
    File report   = "phi_out/report.md"
  }

  runtime {
    docker: docker_image
    cpu:    threads
    memory: memory_gb + " GB"
    disks:  "local-disk " + disk_gb + " SSD"
  }
}

version 1.0

## TCDB 全基因组 / 蛋白注释
##
## 二选一：
##   genome_fasta  -> input_type=nucleic, Prodigal 预测 ORF 后蛋白比对
##   protein_fasta -> input_type=protein, 直接蛋白比对
## 默认 backend=blast（与 v1 一致）；可改为 diamond。
## 全部运行参数在 input 中，不读取 config.yaml。
## 数据库以 String 路径传入，由运行环境挂载，Cromwell 不本地化。

workflow TcdbAnnotatorGenome {
  input {
    String sample_id
    File?  genome_fasta
    File?  protein_fasta

    String blast_db
    String diamond_db
    String metadata
    String db_version = "TCDB 2026-08-23"
    String backend = "blast"

    Int    threads = 8
    String genome_context = "complete"
    Int    min_contig_length = 0
    String tm_prediction = "off"
    String tmbed_model_dir = ""
    String tmbed_module = "tmbed"
    Boolean tmbed_use_gpu = false
    Int    tmbed_batch_size = 1000

    Float min_identity = 30.0
    Float min_query_coverage = 50.0
    Float min_subject_coverage = 0.0
    Float max_evalue = 0.00001
    Int   max_target_seqs = 25
    Int   min_alignment_length = 0

    String blastp_executable = "blastp"
    String blastp_options = ""
    String diamond_executable = "diamond"
    String diamond_options = "--sensitive"
    String prodigal_executable = "prodigal"
    String prodigal_options = ""
    String tmbed_executable = "python"

    Array[String] metadata_fields = [
      "subject_id=subject_id",
      "tcid=tcid",
      "protein_name=protein_name",
      "family_name=family_name",
      "system_name=system_name",
      "description=description",
      "substrate=substrate",
      "organism=organism"
    ]

    String pipeline_dir = "/opt/tcdb-annotator-v2"
    String docker_image = "cncb/tcdb-annotator:v1.0"
    Int    memory_gb = 32
    Int    disk_gb = 100
  }

  call RunTcdbGenome {
    input:
      sample_id            = sample_id,
      genome_fasta         = genome_fasta,
      protein_fasta        = protein_fasta,
      blast_db             = blast_db,
      diamond_db           = diamond_db,
      metadata             = metadata,
      db_version           = db_version,
      backend              = backend,
      threads              = threads,
      genome_context       = genome_context,
      min_contig_length    = min_contig_length,
      tm_prediction        = tm_prediction,
      tmbed_model_dir      = tmbed_model_dir,
      tmbed_module         = tmbed_module,
      tmbed_use_gpu        = tmbed_use_gpu,
      tmbed_batch_size     = tmbed_batch_size,
      min_identity         = min_identity,
      min_query_coverage   = min_query_coverage,
      min_subject_coverage = min_subject_coverage,
      max_evalue           = max_evalue,
      max_target_seqs      = max_target_seqs,
      min_alignment_length = min_alignment_length,
      blastp_executable    = blastp_executable,
      blastp_options       = blastp_options,
      diamond_executable   = diamond_executable,
      diamond_options      = diamond_options,
      prodigal_executable  = prodigal_executable,
      prodigal_options     = prodigal_options,
      tmbed_executable     = tmbed_executable,
      metadata_fields      = metadata_fields,
      pipeline_dir         = pipeline_dir,
      docker_image         = docker_image,
      memory_gb            = memory_gb,
      disk_gb              = disk_gb
  }

  output {
    File hits           = RunTcdbGenome.hits
    File summary        = RunTcdbGenome.summary
    File tm_predictions = RunTcdbGenome.tm_predictions
    File qc             = RunTcdbGenome.qc
    File status         = RunTcdbGenome.status
    File manifest       = RunTcdbGenome.manifest
    File report         = RunTcdbGenome.report
    String sample       = sample_id
  }
}

task RunTcdbGenome {
  input {
    String sample_id
    File?  genome_fasta
    File?  protein_fasta

    String blast_db
    String diamond_db
    String metadata
    String db_version
    String backend

    Int     threads
    String  genome_context
    Int     min_contig_length
    String  tm_prediction
    String  tmbed_model_dir
    String  tmbed_module
    Boolean tmbed_use_gpu
    Int     tmbed_batch_size

    Float min_identity
    Float min_query_coverage
    Float min_subject_coverage
    Float max_evalue
    Int   max_target_seqs
    Int   min_alignment_length

    String blastp_executable
    String blastp_options
    String diamond_executable
    String diamond_options
    String prodigal_executable
    String prodigal_options
    String tmbed_executable
    Array[String] metadata_fields

    String pipeline_dir
    String docker_image
    Int    memory_gb
    Int    disk_gb
  }

  command <<<
    set -euo pipefail
    export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
    export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"

    GENOME="~{genome_fasta}"
    PROTEIN="~{protein_fasta}"
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

    OUT_DIR="$PWD/tcdb_out"
    mkdir -p "$OUT_DIR"

    EXTRA_ARGS=()
    if [[ "$INPUT_TYPE" == "nucleic" ]]; then
      EXTRA_ARGS+=(--genome-context "~{genome_context}" --min-contig-length ~{min_contig_length})
    fi
    if [[ -n "~{tmbed_model_dir}" ]]; then
      EXTRA_ARGS+=(--tmbed-model-dir "~{tmbed_model_dir}")
    fi
    if [[ -n "~{blastp_options}" ]]; then
      EXTRA_ARGS+=(--blastp-options="~{blastp_options}")
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
      --backend "~{backend}" \
      --tm-prediction "~{tm_prediction}" \
      --threads ~{threads} \
      --blast-db "~{blast_db}" \
      --diamond-db "~{diamond_db}" \
      --metadata "~{metadata}" \
      --db-version "~{db_version}" \
      --blastp-executable "~{blastp_executable}" \
      --diamond-executable "~{diamond_executable}" \
      --prodigal-executable "~{prodigal_executable}" \
      --tmbed-executable "~{tmbed_executable}" \
      --tmbed-module "~{tmbed_module}" \
      ~{if tmbed_use_gpu then "--tmbed-use-gpu" else "--no-tmbed-use-gpu"} \
      --tmbed-batch-size ~{tmbed_batch_size} \
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
    File hits           = "tcdb_out/tcdb_hits.tsv"
    File summary        = "tcdb_out/tcdb_summary.tsv"
    File tm_predictions = "tcdb_out/tm_predictions.tsv"
    File qc             = "tcdb_out/qc.json"
    File status         = "tcdb_out/status.json"
    File manifest       = "tcdb_out/manifest.json"
    File report         = "tcdb_out/report.md"
  }

  runtime {
    docker: docker_image
    cpu:    threads
    memory: memory_gb + " GB"
    disks:  "local-disk " + disk_gb + " SSD"
  }
}

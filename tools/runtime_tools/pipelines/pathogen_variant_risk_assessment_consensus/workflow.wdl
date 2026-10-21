version 1.0

# =============================================================================
# Consensus FASTA → VCF → snpEff → risk annotation pipeline
#
# 参考序列、注释库等来自 workflow input（inputs.json）；
# Python 脚本已打入 Docker 镜像 /app/bin_consensus/{h1n1,h3n2,sars_cov2}/。
#
# Cromwell:
#   java -jar cromwell.jar run genomic/wdl/consensus_risk.wdl --inputs genomic/wdl/inputs.example.json
#
# 构建镜像（在 risk/ 目录）：
#   docker build -t risk-wdl:latest -f wdl/Dockerfile .
# =============================================================================

workflow ConsensusRisk {
  input {
    String sample_id
    String pathogen
    String log_tag

    File   consensus_fasta

    File   reference_fasta
    File   snpeff_config
    String snpeff_db
    File   snpeff_data_tarball
    File   segments_tsv
    String reference_label

    File?  risk_annotation_h
    File?  risk_annotation_n
    File?  spike_risk_annotation

    Int   threads = 4
    Int   snpeff_java_mem_gb = 32

    String docker_image = "risk-wdl:latest"
    Int    cpu = 4
    Int    memory_gb = 32
    Int    disk_gb = 100
  }

  call RunConsensusRisk {
    input:
      sample_id                   = sample_id,
      pathogen                    = pathogen,
      log_tag                     = log_tag,
      consensus_fasta             = consensus_fasta,
      reference_fasta             = reference_fasta,
      snpeff_config               = snpeff_config,
      snpeff_db                   = snpeff_db,
      snpeff_data_tarball         = snpeff_data_tarball,
      segments_tsv                = segments_tsv,
      reference_label             = reference_label,
      risk_annotation_h           = risk_annotation_h,
      risk_annotation_n           = risk_annotation_n,
      spike_risk_annotation       = spike_risk_annotation,
      threads                     = threads,
      snpeff_java_mem_gb          = snpeff_java_mem_gb,
      docker_image                = docker_image,
      cpu                         = cpu,
      memory_gb                   = memory_gb,
      disk_gb                     = disk_gb
  }

  output {
    File final_report = RunConsensusRisk.final_report
    File output_tar   = RunConsensusRisk.output_tar
  }
}

task RunConsensusRisk {
  input {
    String sample_id
    String pathogen
    String log_tag
    File   consensus_fasta
    File   reference_fasta
    File   snpeff_config
    String snpeff_db
    File   snpeff_data_tarball
    File   segments_tsv
    String reference_label
    File?  risk_annotation_h
    File?  risk_annotation_n
    File?  spike_risk_annotation
    Int    threads
    Int    snpeff_java_mem_gb
    String docker_image
    Int    cpu
    Int    memory_gb
    Int    disk_gb
  }

  String outdir = "output"

  command <<<
    set -euo pipefail

    mkdir -p snpEff
    tar -xf ~{snpeff_data_tarball} -C snpEff

    # snpEff -dataDir 指向基因组库父目录（与 VariantRisk / xq/run_h1n1.sh 一致），
    # tarball 常见结构为 snpEff/Influenza_A_H1N1/...，不一定有 data/ 子目录
    SNPEFF_DATA_DIR=""
    predictor="$(find snpEff -type f \( -name 'snpEffectPredictor.bin' -o -name 'snpEffect_predictor.bin' \) 2>/dev/null | head -1 || true)"
    if [ -n "$predictor" ]; then
      genome_dir="$(dirname "$predictor")"
      SNPEFF_DATA_DIR="$(cd "$(dirname "$genome_dir")" && pwd)"
    fi
    if [ -z "$SNPEFF_DATA_DIR" ] || [ ! -d "$SNPEFF_DATA_DIR" ]; then
      if [ -d snpEff/data ]; then
        SNPEFF_DATA_DIR="$(pwd)/snpEff/data"
      elif [ -d snpEff/snpEff/data ]; then
        SNPEFF_DATA_DIR="$(pwd)/snpEff/snpEff/data"
      fi
    fi
    if [ -z "$SNPEFF_DATA_DIR" ] || [ ! -d "$SNPEFF_DATA_DIR" ]; then
      echo "Cannot locate snpEff data directory inside tarball" >&2
      echo "Extracted layout:" >&2
      find snpEff -maxdepth 4 2>/dev/null | head -50 >&2
      exit 1
    fi

    export SAMPLE_ID="~{sample_id}"
    export PATHOGEN="~{pathogen}"
    export LOG_TAG="~{log_tag}"
    export REF="~{reference_fasta}"
    export SNPEFF_CONFIG="~{snpeff_config}"
    export SNPEFF_DATA_DIR
    export SNPEFF_DB_NAME="~{snpeff_db}"
    export SEGMENTS="~{segments_tsv}"
    export REFERENCE_LABEL="~{reference_label}"
    export RISK_ANNOTATION_H="~{if defined(risk_annotation_h) then select_first([risk_annotation_h]) else ''}"
    export RISK_ANNOTATION_N="~{if defined(risk_annotation_n) then select_first([risk_annotation_n]) else ''}"
    export SPIKE_RISK_ANNOTATION="~{if defined(spike_risk_annotation) then select_first([spike_risk_annotation]) else ''}"

    source /app/lib/docker_consensus_bin_paths.sh

    export THREADS="~{threads}"
    export SNPEFF_JAVA_MEM_GB="~{snpeff_java_mem_gb}"

    bash /app/run_consensus_risk.sh \
      -p "~{pathogen}" \
      -i "~{consensus_fasta}" \
      -o "~{outdir}"

    tar -cf ~{sample_id}.output.tar -C ~{outdir} .
  >>>

  output {
    File final_report = "~{outdir}/report/~{sample_id}.final_variant_risk_report.tsv"
    File output_tar   = "~{sample_id}.output.tar"
  }

  runtime {
    docker: docker_image
    cpu:    cpu
    memory: "~{memory_gb} GB"
    disks:  "local-disk ~{disk_gb} SSD"
  }
}

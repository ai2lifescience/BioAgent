version 1.0

workflow VariantRisk {
  input {
    String sample_id
    String pathogen
    String log_tag

    File   fastq_r1
    File?  fastq_r2

    File   reference_fasta
    File   snpeff_config
    String snpeff_db
    File   snpeff_data_tarball
    File   segments_tsv
    String reference_label

    File?  risk_annotation_h
    File?  risk_annotation_n
    File?  spike_risk_annotation

    Int   threads = 8
    Int   mapq = 20
    Int   baseq = 20
    Float ivar_min_depth = 2.0
    Float ivar_min_af = 0.6
    Float highconf_depth = 20.0
    Float highconf_af = 0.05
    Int   segment_depth_threshold = 5
    Int   trim_bp = 3
    Int   snpeff_java_mem_gb = 32

    String docker_image = "variant-risk-wdl:latest"
    Int    cpu = 8
    Int    memory_gb = 64
    Int    disk_gb = 200
  }

  call RunVariantRisk {
    input:
      sample_id                   = sample_id,
      pathogen                    = pathogen,
      log_tag                     = log_tag,
      fastq_r1                    = fastq_r1,
      fastq_r2                    = fastq_r2,
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
      mapq                        = mapq,
      baseq                       = baseq,
      ivar_min_depth              = ivar_min_depth,
      ivar_min_af                 = ivar_min_af,
      highconf_depth              = highconf_depth,
      highconf_af                 = highconf_af,
      segment_depth_threshold     = segment_depth_threshold,
      trim_bp                     = trim_bp,
      snpeff_java_mem_gb          = snpeff_java_mem_gb,
      docker_image                = docker_image,
      cpu                         = cpu,
      memory_gb                   = memory_gb,
      disk_gb                     = disk_gb
  }

  output {
    File final_report = RunVariantRisk.final_report
    File segments     = RunVariantRisk.segments
    File output_tar   = RunVariantRisk.output_tar
  }
}

task RunVariantRisk {
  input {
    String sample_id
    String pathogen
    String log_tag
    File   fastq_r1
    File?  fastq_r2
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
    Int    mapq
    Int    baseq
    Float  ivar_min_depth
    Float  ivar_min_af
    Float  highconf_depth
    Float  highconf_af
    Int    segment_depth_threshold
    Int    trim_bp
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

    # snpEff -dataDir 指向基因组库父目录（与 xq/run_h1n1.sh 一致），
    # 不要求存在 data/ 子目录；tarball 常见结构为 snpEff/Influenza_A_H1N1/...
    SNPEFF_DATA_DIR=""
    predictor="$(find snpEff -type f \( -name 'snpEffectPredictor.bin' -o -name 'snpEffect_predictor.bin' \) 2>/dev/null | head -1 || true)"
    if [ -n "$predictor" ]; then
      genome_dir="$(dirname "$predictor")"
      SNPEFF_DATA_DIR="$(cd "$(dirname "$genome_dir")" && pwd)"
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

    REF_PATH="~{reference_fasta}"
    # Cromwell 仅本地化 FASTA，宿主机预建的 .bwt/.fai 不会带入容器，缺失时现场构建
    if [ ! -s "${REF_PATH}.bwt" ]; then
      echo "[VariantRisk] No BWA index (${REF_PATH}.bwt); running bwa index..."
      bwa index "$REF_PATH"
    fi
    if [ ! -s "${REF_PATH}.fai" ]; then
      echo "[VariantRisk] Running samtools faidx for mpileup..."
      samtools faidx "$REF_PATH"
    fi
    export REF="$REF_PATH"

    export SNPEFF_CONFIG="~{snpeff_config}"
    export SNPEFF_DATA_DIR
    export SNPEFF_DB_NAME="~{snpeff_db}"
    export SEGMENTS="~{segments_tsv}"
    export REFERENCE_LABEL="~{reference_label}"
    export RISK_ANNOTATION_H="~{if defined(risk_annotation_h) then select_first([risk_annotation_h]) else ''}"
    export RISK_ANNOTATION_N="~{if defined(risk_annotation_n) then select_first([risk_annotation_n]) else ''}"
    export SPIKE_RISK_ANNOTATION="~{if defined(spike_risk_annotation) then select_first([spike_risk_annotation]) else ''}"

    source /app/lib/docker_bin_paths.sh

    export THREADS="~{threads}"
    export MAPQ="~{mapq}"
    export BASEQ="~{baseq}"
    export IVAR_MIN_DEPTH="~{ivar_min_depth}"
    export IVAR_MIN_AF="~{ivar_min_af}"
    export HIGHCONF_DEPTH="~{highconf_depth}"
    export HIGHCONF_AF="~{highconf_af}"
    export SEGMENT_DEPTH_THRESHOLD="~{segment_depth_threshold}"
    export TRIM_BP="~{trim_bp}"
    export SNPEFF_JAVA_MEM_GB="~{snpeff_java_mem_gb}"

    if [ -n "~{if defined(fastq_r2) then select_first([fastq_r2]) else ''}" ]; then
      bash /app/run_variant_risk.sh \
        -p "~{pathogen}" \
        -i "~{fastq_r1}" \
        -i2 "~{if defined(fastq_r2) then select_first([fastq_r2]) else ''}" \
        -o "~{outdir}"
    else
      bash /app/run_variant_risk.sh \
        -p "~{pathogen}" \
        -i "~{fastq_r1}" \
        -o "~{outdir}"
    fi

    tar -cf ~{sample_id}.output.tar -C ~{outdir} .
  >>>

  output {
    File final_report = "~{outdir}/report/~{sample_id}.final_variant_risk_report.tsv"
    File segments     = "~{outdir}/report/~{sample_id}.segments.tsv"
    File output_tar   = "~{sample_id}.output.tar"
  }

  runtime {
    docker: docker_image
    cpu:    cpu
    memory: "~{memory_gb} GB"
    disks:  "local-disk ~{disk_gb} SSD"
  }
}

version 1.0

# Stage 0 only: read QC and host removal (fastp -> kraken2 -> bowtie2).
# Its outputs are the file-level contract consumed by pipeline.wdl.
workflow MetagenomicQc {
  input {
    String      sample_id
    File        fastq_r1
    File?       fastq_r2
    Array[String] kraken2_db_files
    Array[String] host_bowtie2_index_files

    Boolean lean_io_mode = true
    String  docker_image = "mscan-detection-qc:latest"
    Int     cpu           = 8
    Int     memory_gb     = 64
    Int     disk_gb       = 500
  }

  Boolean paired_end = defined(fastq_r2)

  if (paired_end) {
    call QcAndHostRemovalPe {
      input:
        sample_id                 = sample_id,
        fastq_r1                  = fastq_r1,
        fastq_r2                  = select_first([fastq_r2]),
        kraken2_db_files          = kraken2_db_files,
        host_bowtie2_index_files  = host_bowtie2_index_files,
        threads                   = cpu,
        lean_io_mode              = lean_io_mode,
        docker_image              = docker_image,
        cpu                       = cpu,
        memory_gb                 = memory_gb,
        disk_gb                   = disk_gb
    }
  }

  if (!paired_end) {
    call QcAndHostRemovalSe {
      input:
        sample_id                 = sample_id,
        fastq_r1                  = fastq_r1,
        kraken2_db_files          = kraken2_db_files,
        host_bowtie2_index_files  = host_bowtie2_index_files,
        threads                   = cpu,
        lean_io_mode              = lean_io_mode,
        docker_image              = docker_image,
        cpu                       = cpu,
        memory_gb                 = memory_gb,
        disk_gb                   = disk_gb
    }
  }

  output {
    File clean_r1          = select_first([QcAndHostRemovalPe.clean_r1, QcAndHostRemovalSe.clean_r1])
    File? clean_r2         = QcAndHostRemovalPe.clean_r2
    Int  post_host_reads   = select_first([QcAndHostRemovalPe.post_host_reads, QcAndHostRemovalSe.post_host_reads])
    File qc_counts         = select_first([QcAndHostRemovalPe.qc_counts, QcAndHostRemovalSe.qc_counts])
    File phase1_metrics    = select_first([QcAndHostRemovalPe.phase1_metrics, QcAndHostRemovalSe.phase1_metrics])
  }
}

task QcAndHostRemovalPe {
  input {
    String      sample_id
    File        fastq_r1
    File        fastq_r2
    Array[String] kraken2_db_files
    Array[String] host_bowtie2_index_files
    Int         threads
    Boolean     lean_io_mode
    String      docker_image
    Int         cpu
    Int         memory_gb
    Int         disk_gb
  }

  String prep_dir = "02.rm_human"

  command <<<
    set -euo pipefail
    SAMPLE="~{sample_id}"
    PREP="~{prep_dir}"
    mkdir -p "$PREP"

    count_reads() { python3 /app/scripts/count_reads.py "$1"; }
    KR_DB="$(dirname '~{kraken2_db_files[0]}')"
    BT2_F="~{host_bowtie2_index_files[0]}"
    BT2_IDX="${BT2_F%.1.bt2l}"; BT2_IDX="${BT2_IDX%.1.bt2}"

    FASTP_BASE="--length_required 35 -x -w ~{threads} --cut_tail --cut_tail_mean_quality 5"
    FASTP_IO="-i ~{fastq_r1} -I ~{fastq_r2} -o ${PREP}/${SAMPLE}.QC.R1.fq -O ${PREP}/${SAMPLE}.QC.R2.fq"
    if [ "~{lean_io_mode}" = "true" ]; then
      fastp ${FASTP_IO} ${FASTP_BASE}
    else
      fastp ${FASTP_IO} ${FASTP_BASE} --json "${PREP}/${SAMPLE}.json" --html "${PREP}/${SAMPLE}.html"
    fi

    KR_REPORT="${PREP}/${SAMPLE}.rmhuman.k2.kreport"
    kraken2 --memory-mapping --db "$KR_DB" --paired \
      --unclassified-out "${PREP}/${SAMPLE}.rmhuman.tmp.unmap#.fq" \
      "${PREP}/${SAMPLE}.QC.R1.fq" "${PREP}/${SAMPLE}.QC.R2.fq" \
      --threads ~{threads} --report "$KR_REPORT" --output /dev/null

    if [ -f "${PREP}/${SAMPLE}.rmhuman.tmp.unmap_1.fq" ]; then
      TMP_R1="${PREP}/${SAMPLE}.rmhuman.tmp.unmap_1.fq"; TMP_R2="${PREP}/${SAMPLE}.rmhuman.tmp.unmap_2.fq"
    elif [ -f "${PREP}/${SAMPLE}.rmhuman.tmp.unmap1.fq" ]; then
      TMP_R1="${PREP}/${SAMPLE}.rmhuman.tmp.unmap1.fq"; TMP_R2="${PREP}/${SAMPLE}.rmhuman.tmp.unmap2.fq"
    else
      TMP_R1="${PREP}/${SAMPLE}.rmhuman.tmp.unmap.1.fq"; TMP_R2="${PREP}/${SAMPLE}.rmhuman.tmp.unmap.2.fq"
    fi

    bowtie2 --threads ~{threads} -x "$BT2_IDX" -1 "$TMP_R1" -2 "$TMP_R2" \
      --very-sensitive -S /dev/null --un-conc "${PREP}/${SAMPLE}.clean.R%.fq"
    TOTAL=$(count_reads "~{fastq_r1}")
    QC_PASSED=$(count_reads "${PREP}/${SAMPLE}.QC.R1.fq")
    POST_HOST=$(count_reads "${PREP}/${SAMPLE}.clean.R1.fq")
    printf 'MetricName\tMetricValue\nInputReads\t%s\nReadsAfterQC\t%s\nReadsAfterHostRemoval\t%s\n' \
      "$TOTAL" "$QC_PASSED" "$POST_HOST" > "${SAMPLE}.stage0.input_qc_counts.tsv"
    printf 'SampleId\tInputReads\tReadsAfterQC\tReadsAfterHostRemoval\n%s\t%s\t%s\t%s\n' \
      "$SAMPLE" "$TOTAL" "$QC_PASSED" "$POST_HOST" > "${SAMPLE}.run.phase1_read_overview.tsv"
    echo "$POST_HOST" > post_host_reads.txt
  >>>

  output {
    File clean_r1        = "~{prep_dir}/~{sample_id}.clean.R1.fq"
    File clean_r2        = "~{prep_dir}/~{sample_id}.clean.R2.fq"
    File qc_counts       = "~{sample_id}.stage0.input_qc_counts.tsv"
    File phase1_metrics  = "~{sample_id}.run.phase1_read_overview.tsv"
    Int  post_host_reads = read_int("post_host_reads.txt")
  }

  runtime {
    docker: docker_image
    cpu: cpu
    memory: "~{memory_gb} GB"
    disks: "local-disk ~{disk_gb} SSD"
  }
}

task QcAndHostRemovalSe {
  input {
    String      sample_id
    File        fastq_r1
    Array[String] kraken2_db_files
    Array[String] host_bowtie2_index_files
    Int         threads
    Boolean     lean_io_mode
    String      docker_image
    Int         cpu
    Int         memory_gb
    Int         disk_gb
  }

  String prep_dir = "02.rm_human"

  command <<<
    set -euo pipefail
    SAMPLE="~{sample_id}"
    PREP="~{prep_dir}"
    mkdir -p "$PREP"

    count_reads() { python3 /app/scripts/count_reads.py "$1"; }
    KR_DB="$(dirname '~{kraken2_db_files[0]}')"
    BT2_F="~{host_bowtie2_index_files[0]}"
    BT2_IDX="${BT2_F%.1.bt2l}"; BT2_IDX="${BT2_IDX%.1.bt2}"

    FASTP_BASE="--length_required 35 -x -w ~{threads} --cut_tail --cut_tail_mean_quality 5"
    FASTP_IO="-i ~{fastq_r1} -o ${PREP}/${SAMPLE}.QC.fq"
    if [ "~{lean_io_mode}" = "true" ]; then
      fastp ${FASTP_IO} ${FASTP_BASE}
    else
      fastp ${FASTP_IO} ${FASTP_BASE} --json "${PREP}/${SAMPLE}.json" --html "${PREP}/${SAMPLE}.html"
    fi

    KR_REPORT="${PREP}/${SAMPLE}.rmhuman.k2.kreport"
    kraken2 --memory-mapping --db "$KR_DB" \
      --unclassified-out "${PREP}/${SAMPLE}.rmhuman.tmp.unmap.fq" \
      "${PREP}/${SAMPLE}.QC.fq" --threads ~{threads} --report "$KR_REPORT" --output /dev/null
    bowtie2 --threads ~{threads} -x "$BT2_IDX" -U "${PREP}/${SAMPLE}.rmhuman.tmp.unmap.fq" \
      --very-sensitive -S /dev/null --un "${PREP}/${SAMPLE}.clean.fq"
    TOTAL=$(count_reads "~{fastq_r1}")
    QC_PASSED=$(count_reads "${PREP}/${SAMPLE}.QC.fq")
    POST_HOST=$(count_reads "${PREP}/${SAMPLE}.clean.fq")
    printf 'MetricName\tMetricValue\nInputReads\t%s\nReadsAfterQC\t%s\nReadsAfterHostRemoval\t%s\n' \
      "$TOTAL" "$QC_PASSED" "$POST_HOST" > "${SAMPLE}.stage0.input_qc_counts.tsv"
    printf 'SampleId\tInputReads\tReadsAfterQC\tReadsAfterHostRemoval\n%s\t%s\t%s\t%s\n' \
      "$SAMPLE" "$TOTAL" "$QC_PASSED" "$POST_HOST" > "${SAMPLE}.run.phase1_read_overview.tsv"
    echo "$POST_HOST" > post_host_reads.txt
  >>>

  output {
    File clean_r1        = "~{prep_dir}/~{sample_id}.clean.fq"
    File qc_counts       = "~{sample_id}.stage0.input_qc_counts.tsv"
    File phase1_metrics  = "~{sample_id}.run.phase1_read_overview.tsv"
    Int  post_host_reads = read_int("post_host_reads.txt")
  }

  runtime {
    docker: docker_image
    cpu: cpu
    memory: "~{memory_gb} GB"
    disks: "local-disk ~{disk_gb} SSD"
  }
}
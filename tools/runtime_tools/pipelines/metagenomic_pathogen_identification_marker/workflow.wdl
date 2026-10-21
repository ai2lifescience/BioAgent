version 1.0

## Strain Meta — Step 1: 单样本 MetaPhlAn4 + sample2markers（SE / PE）
##
## 镜像: cncb/strain-meta:v1.0（metaphlan + sample2markers）
##
## 构建: bash wdl/build_images.sh
## 提交:
##   java -jar cromwell.jar run strain_meta.wdl \
##     --inputs inputs_meta.example.json \
##     -Dconfig.file=wdl/cromwell.conf

workflow StrainMeta {
  input {
    String sample_id
    String data_type = "metagenome"

    File  fastq_r1
    File? fastq_r2

    String metaphlan_db_dir
    String metaphlan_db_index

    Int threads = 16

    String docker_image = "cncb/strain-meta:v1.0"
    Int cpu = 16
    Int memory_gb = 64
    Int disk_gb = 500
  }

  String task_out = "strain_meta_" + sample_id

  call MetaPhlAnSample {
    input:
      sample_id          = sample_id,
      fastq_r1           = fastq_r1,
      fastq_r2           = fastq_r2,
      data_type          = data_type,
      task_out           = task_out,
      metaphlan_db_dir   = metaphlan_db_dir,
      metaphlan_db_index = metaphlan_db_index,
      threads            = threads,
      docker_image       = docker_image,
      cpu                = cpu,
      memory_gb          = memory_gb,
      disk_gb            = disk_gb
  }

  output {
    File profile          = MetaPhlAnSample.profile
    File sam_bz2          = MetaPhlAnSample.sam_bz2
    File consensus_marker = MetaPhlAnSample.marker_file
    String output_prefix  = task_out
  }
}


task MetaPhlAnSample {
  input {
    String sample_id
    File   fastq_r1
    File?  fastq_r2
    String data_type
    String task_out

    String metaphlan_db_dir
    String metaphlan_db_index
    Int    threads

    String docker_image
    Int    cpu
    Int    memory_gb
    Int    disk_gb
  }

  command <<<
    set -euo pipefail
    export MPLBACKEND=agg

    OUT_DIR="~{task_out}"
    mkdir -p "${OUT_DIR}"

    export METAPHLAN_DB_DIR="~{metaphlan_db_dir}"
    export METAPHLAN_BOWTIE2DB="~{metaphlan_db_dir}"
    DB_PKL="~{metaphlan_db_dir}/~{metaphlan_db_index}.pkl"
    if [ ! -f "${DB_PKL}" ]; then
      echo "[ERROR] MetaPhlAn DB not visible in container: ${DB_PKL}" >&2
      echo "[HINT]  确认 cromwell.conf 已挂载 -v /data:/data，且 inputs 中 metaphlan_db_dir 正确" >&2
      ls -la "~{metaphlan_db_dir}" 2>&1 || true
      exit 1
    fi

    R2_ARG=""
    if [ -n "~{fastq_r2}" ] && [ -f "~{fastq_r2}" ]; then
      R2_ARG="-2 ~{fastq_r2}"
    fi

    bash /app/scripts/run_metaphlan_sample.sh \
      -s "~{sample_id}" \
      -1 "~{fastq_r1}" \
      ${R2_ARG} \
      -t "~{data_type}" \
      -o "${OUT_DIR}" \
      --db-dir "~{metaphlan_db_dir}" \
      --db-index "~{metaphlan_db_index}" \
      --threads ~{threads}

    cp "${OUT_DIR}/profiles/~{sample_id}_profile.txt" profile.txt
    cp "${OUT_DIR}/sams/~{sample_id}.sam.bz2" sam.bz2
    cp "${OUT_DIR}/bowtie2/~{sample_id}.bowtie2.bz2" bowtie2.bz2

    MARKER="$(find "${OUT_DIR}/consensus_markers" -maxdepth 1 -type f \
      \( -name "~{sample_id}.json.bz2" -o -name "~{sample_id}.pkl" -o -name "~{sample_id}.pkl.bz2" \) \
      | head -n1 || true)"
    MARKER_OUT="~{sample_id}.json.bz2"
    if [ -n "${MARKER}" ] && [ -s "${MARKER}" ]; then
      cp "${MARKER}" "${MARKER_OUT}"
    else
      touch "${MARKER_OUT}"
      echo "[WARN] no marker for ~{sample_id}" >&2
    fi
  >>>

  output {
    File profile      = "profile.txt"
    File sam_bz2      = "sam.bz2"
    File marker_file = sample_id + ".json.bz2"
  }

  runtime {
    docker: docker_image
    cpu:    cpu
    memory: memory_gb + " GB"
    disks:  "local-disk " + disk_gb + " SSD"
  }
}

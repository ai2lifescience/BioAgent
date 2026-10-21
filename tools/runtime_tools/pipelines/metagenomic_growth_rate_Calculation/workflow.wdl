version 1.0

## Strain CoPTR — 单样本 宏基因组 reads → 生长速度 log2(PTR)
##
## 流程: index(可复用) -> map -> extract -> estimate
## 输出: genome × sample 的 log2(PTR) 表 (CSV)
##
## 镜像: cncb/strain-coptr:v1.0（coptr + bowtie2 + samtools + NumPy2 兼容补丁）
## 构建: bash wdl/build_images.sh
## 提交:
##   java -jar cromwell.jar run strain_coptr.wdl \
##     --inputs inputs_coptr.example.json \
##     -Dconfig.file=wdl/cromwell.conf
##
## 说明:
##   - coptr_ref_dir / coptr_index_dir 为宿主绝对路径，靠 cromwell.conf 的
##     -v /data:/data:ro 挂载进容器，故用 String 而非 File
##   - 索引已存在(.genomes 文件在)则复用，否则在工作目录里现建
##   - SE / PE 由 fastq_r2 是否提供决定

workflow StrainCoPTR {
  input {
    String sample_id
    File   fastq_r1
    File?  fastq_r2

    String coptr_ref_dir
    String coptr_index_dir

    Int    min_reads   = 2500
    Int    threads     = 16

    String docker_image = "cncb/strain-coptr:v1.0"
    Int    cpu          = 16
    Int    memory_gb    = 64
    Int    disk_gb      = 500
  }

  String task_out = "strain_coptr_" + sample_id

  call CoPTRSample {
    input:
      sample_id       = sample_id,
      fastq_r1        = fastq_r1,
      fastq_r2        = fastq_r2,
      task_out        = task_out,
      coptr_ref_dir   = coptr_ref_dir,
      coptr_index_dir = coptr_index_dir,
      min_reads       = min_reads,
      threads         = threads,
      docker_image    = docker_image,
      cpu             = cpu,
      memory_gb       = memory_gb,
      disk_gb         = disk_gb
  }

  output {
    File   log2ptr_csv    = CoPTRSample.log2ptr_csv
    String output_prefix  = task_out
  }
}


task CoPTRSample {
  input {
    String sample_id
    File   fastq_r1
    File?  fastq_r2
    String task_out

    String coptr_ref_dir
    String coptr_index_dir
    Int    min_reads
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

    if [ ! -d "~{coptr_ref_dir}" ]; then
      echo "[ERROR] CoPTR ref genome dir not visible in container: ~{coptr_ref_dir}" >&2
      echo "[HINT]  确认 cromwell.conf 已挂载 -v /data:/data:ro，且 inputs 中 coptr_ref_dir 正确" >&2
      ls -la "$(dirname "~{coptr_ref_dir}")" 2>&1 || true
      exit 1
    fi

    R2_ARG=""
    if [ -n "~{fastq_r2}" ] && [ -f "~{fastq_r2}" ]; then
      R2_ARG="-2 ~{fastq_r2}"
    fi

    bash /app/scripts/run_coptr_sample.sh \
      -n "~{sample_id}" \
      -1 "~{fastq_r1}" \
      ${R2_ARG} \
      -o "${OUT_DIR}" \
      --ref-dir   "~{coptr_ref_dir}" \
      --index-dir "~{coptr_index_dir}" \
      --min-reads ~{min_reads} \
      --threads   ~{threads}

    cp "${OUT_DIR}/result/~{sample_id}_coptr_log2ptr.csv" ~{sample_id}_coptr_log2ptr.csv
  >>>

  output {
    File log2ptr_csv = sample_id + "_coptr_log2ptr.csv"
  }

  runtime {
    docker: docker_image
    cpu:    cpu
    memory: memory_gb + " GB"
    disks:  "local-disk " + disk_gb + " SSD"
  }
}

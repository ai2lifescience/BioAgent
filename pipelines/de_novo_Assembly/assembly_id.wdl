version 1.0

# =============================================================================
# 宏基因组组装与鉴定 Pipeline（Assembly & ID）— Cromwell / WDL 版
#
# 对应 bash 流程 main.sh 四步：
#   Assembly (MEGAHIT) → ReadSupport → Identify (minimap2) → Evaluate (MetaQUAST)
#
# 镜像内含工具与脚本；大库（.mmi / .fa）与注释表以 File 输入交由 Cromwell 后端本地化。
#
# 构建（在 assembly_id_pipeline/ 目录）:
#   bash wdl/build_images.sh
#
# 提交:
#   java -jar cromwell.jar run wdl/assembly_id.wdl \
#     --inputs wdl/inputs.example.json \
#     -Dconfig.file=wdl/cromwell.conf
# =============================================================================

workflow AssemblyId {
  input {
    String sample_id
    File   fastq_r1
    File?  fastq_r2

    # 鉴定库（minimap2 索引）；File 输入由 WDL 引擎挂载到任务容器
    String db_bacteria
    String db_fungi
    String db_parasite
    String db_virus

    # 物种注释表
    String annot_pathogen
    String annot_virus

    # 原始 FASTA 用于索引缺失时回退比对以及可选 MetaQUAST 评估
    String? fasta_bacteria
    String? fasta_fungi
    String? fasta_parasite
    String? fasta_virus

    # 是否跑 MetaQUAST（默认 true；调试可设 false）
    Boolean do_evaluate = true

    # MEGAHIT
    Int    megahit_min_contig_len = 100
    String megahit_k_list = "15,21,29,39"
    String megahit_extra_params = "--min-count 1"

    # minimap2
    String minimap2_params = "-x asm20 -N 5"
    String minimap2_read_params = "-ax sr --secondary=no"

    # soft clipping 阈值
    Int   softclip_min_clip = 5
    Int   softclip_min_reads = 3
    Float softclip_min_fraction = 0.2
    Int   softclip_edge_bp = 10

    # MetaQUAST
    Int    max_unique_references = 100
    String metaquast_params = "--no-plots --no-html --no-icarus --fast"

    Int threads = 32

    String docker_image = "cncb/assembly-id:v1.0"
    Int cpu_assembly = 32
    Int cpu_map = 32
    Int cpu_eval = 16
    Int mem_assembly_gb = 64
    Int mem_map_gb = 64
    Int mem_eval_gb = 32
    Int disk_gb = 500
  }

  String work_base = "assembly_id_" + sample_id

  call Assembly {
    input:
      sample_id              = sample_id,
      fastq_r1               = fastq_r1,
      fastq_r2               = fastq_r2,
      work_base              = work_base,
      threads                = threads,
      megahit_min_contig_len = megahit_min_contig_len,
      megahit_k_list         = megahit_k_list,
      megahit_extra_params   = megahit_extra_params,
      docker_image           = docker_image,
      cpu                    = cpu_assembly,
      memory_gb              = mem_assembly_gb,
      disk_gb                = disk_gb
  }

  call ReadSupport {
    input:
      sample_id              = sample_id,
      fastq_r1               = fastq_r1,
      fastq_r2               = fastq_r2,
      contigs                = Assembly.contigs_renamed,
      work_base              = work_base,
      threads                = threads,
      minimap2_read_params   = minimap2_read_params,
      softclip_min_clip      = softclip_min_clip,
      softclip_min_reads     = softclip_min_reads,
      softclip_min_fraction  = softclip_min_fraction,
      softclip_edge_bp       = softclip_edge_bp,
      docker_image           = docker_image,
      cpu                    = cpu_map,
      memory_gb              = mem_map_gb,
      disk_gb                = disk_gb
  }

  call Identify {
    input:
      sample_id         = sample_id,
      contigs           = Assembly.contigs_renamed,
      read_support_tsv  = ReadSupport.read_support_contig_tsv,
      db_bacteria       = db_bacteria,
      db_fungi          = db_fungi,
      db_parasite       = db_parasite,
      db_virus          = db_virus,
      fasta_bacteria    = fasta_bacteria,
      fasta_fungi       = fasta_fungi,
      fasta_parasite    = fasta_parasite,
      fasta_virus       = fasta_virus,
      annot_pathogen    = annot_pathogen,
      annot_virus       = annot_virus,
      work_base         = work_base,
      threads           = threads,
      minimap2_params   = minimap2_params,
      docker_image      = docker_image,
      cpu               = cpu_map,
      memory_gb         = mem_map_gb,
      disk_gb           = disk_gb
  }

  if (do_evaluate) {
    call Evaluate {
      input:
        sample_id              = sample_id,
        contigs_raw            = Assembly.contigs_raw,
        contigs_renamed        = Assembly.contigs_renamed,
        best_hits              = Identify.best_hits_tsv,
        identification_tsv     = Identify.identification_tsv,
        read_support_tsv       = ReadSupport.read_support_contig_tsv,
        fasta_bacteria         = fasta_bacteria,
        fasta_fungi            = fasta_fungi,
        fasta_parasite         = fasta_parasite,
        fasta_virus            = fasta_virus,
        work_base              = work_base,
        threads                = threads,
        max_unique_references  = max_unique_references,
        metaquast_params       = metaquast_params,
        docker_image           = docker_image,
        cpu                    = cpu_eval,
        memory_gb              = mem_eval_gb,
        disk_gb                = disk_gb
    }
  }

  output {
    File final_contigs_renamed = select_first([Evaluate.final_contigs_renamed, Assembly.contigs_renamed])
    File contig_report_tsv     = select_first([Evaluate.contig_report_tsv, Identify.contig_report_tsv])
    File species_report_tsv    = select_first([Evaluate.species_report_tsv, Identify.species_report_tsv])
    Array[File] paf_files      = Identify.paf_files
  }
}


task Assembly {
  input {
    String sample_id
    File   fastq_r1
    File?  fastq_r2
    String work_base
    Int    threads
    Int    megahit_min_contig_len
    String megahit_k_list
    String megahit_extra_params
    String docker_image
    Int    cpu
    Int    memory_gb
    Int    disk_gb
  }

  # Cromwell 对未绑定的 File? 插值为空串；绑定为 File 时会本地化进容器
  command <<<
    set -euo pipefail
    OUT="~{work_base}/01_assembly_work"
    mkdir -p "${OUT}"

    EXTRA_ARGS=()
    if [ -n "~{fastq_r2}" ]; then
      EXTRA_ARGS+=(--r2 "~{fastq_r2}")
    fi

    bash /app/scripts/run_assembly.sh \
      --sample "~{sample_id}" \
      --r1 "~{fastq_r1}" \
      "${EXTRA_ARGS[@]}" \
      --out-dir "${OUT}" \
      --threads ~{threads} \
      --min-contig-len ~{megahit_min_contig_len} \
      --k-list "~{megahit_k_list}" \
      --extra-params "~{megahit_extra_params}"

    mkdir -p outputs
    cp -f "${OUT}/outputs/final.contigs.fa" outputs/final.contigs.fa
    cp -f "${OUT}/outputs/final.contigs.renamed.fa" outputs/final.contigs.renamed.fa
  >>>

  output {
    File contigs_raw     = "outputs/final.contigs.fa"
    File contigs_renamed = "outputs/final.contigs.renamed.fa"
  }

  runtime {
    docker: docker_image
    cpu: cpu
    memory: "~{memory_gb} GB"
    disks: "local-disk ~{disk_gb} SSD"
  }
}


task ReadSupport {
  input {
    String sample_id
    File   fastq_r1
    File?  fastq_r2
    File   contigs
    String work_base
    Int    threads
    String minimap2_read_params
    Int    softclip_min_clip
    Int    softclip_min_reads
    Float  softclip_min_fraction
    Int    softclip_edge_bp
    String docker_image
    Int    cpu
    Int    memory_gb
    Int    disk_gb
  }

  command <<<
    set -euo pipefail
    OUT="~{work_base}/02_read_support_work"
    mkdir -p "${OUT}"

    EXTRA_ARGS=()
    if [ -n "~{fastq_r2}" ]; then
      EXTRA_ARGS+=(--r2 "~{fastq_r2}")
    fi

    bash /app/scripts/run_read_support.sh \
      --sample "~{sample_id}" \
      --r1 "~{fastq_r1}" \
      "${EXTRA_ARGS[@]}" \
      --contigs "~{contigs}" \
      --out-dir "${OUT}" \
      --threads ~{threads} \
      --read-params "~{minimap2_read_params}" \
      --softclip-min-clip ~{softclip_min_clip} \
      --softclip-min-reads ~{softclip_min_reads} \
      --softclip-min-fraction ~{softclip_min_fraction} \
      --softclip-edge-bp ~{softclip_edge_bp}

    mkdir -p outputs
    cp -f "${OUT}/outputs/~{sample_id}_read_support_contig.tsv" outputs/read_support_contig.tsv
    cp -f "${OUT}/outputs/~{sample_id}_read_alignment_summary.tsv" outputs/read_alignment_summary.tsv
    cp -f "${OUT}/outputs/~{sample_id}.reads_to_contigs.bam" outputs/reads_to_contigs.bam
    cp -f "${OUT}/outputs/~{sample_id}.reads_to_contigs.bam.bai" outputs/reads_to_contigs.bam.bai
  >>>

  output {
    File read_support_contig_tsv    = "outputs/read_support_contig.tsv"
    File read_alignment_summary_tsv = "outputs/read_alignment_summary.tsv"
    File reads_to_contigs_bam       = "outputs/reads_to_contigs.bam"
    File reads_to_contigs_bam_bai   = "outputs/reads_to_contigs.bam.bai"
  }

  runtime {
    docker: docker_image
    cpu: cpu
    memory: "~{memory_gb} GB"
    disks: "local-disk ~{disk_gb} SSD"
  }
}


task Identify {
  input {
    String sample_id
    File   contigs
    File   read_support_tsv
    File db_bacteria
    File db_fungi
    File db_parasite
    File db_virus
    File? fasta_bacteria
    File? fasta_fungi
    File? fasta_parasite
    File? fasta_virus
    File annot_pathogen
    File annot_virus
    String work_base
    Int    threads
    String minimap2_params
    String docker_image
    Int    cpu
    Int    memory_gb
    Int    disk_gb
  }

  command <<<
    set -euo pipefail
    trap 'rc=$?; echo "ERROR: Identify task failed at line ${LINENO} (exit code ${rc})" >&2; exit "${rc}"' ERR

    for REQUIRED_FILE in \
      "~{db_bacteria}" \
      "~{db_fungi}" \
      "~{db_parasite}" \
      "~{db_virus}" \
      "~{annot_pathogen}" \
      "~{annot_virus}"; do
      if [ ! -r "${REQUIRED_FILE}" ]; then
        echo "ERROR: required Identify input is not readable in the task container: ${REQUIRED_FILE}" >&2
        exit 2
      fi
    done

    OUT="~{work_base}/03_identify_work"
    mkdir -p "${OUT}"

    bash /app/scripts/run_identify.sh \
      --sample "~{sample_id}" \
      --contigs "~{contigs}" \
      --read-support-tsv "~{read_support_tsv}" \
      --out-dir "${OUT}" \
      --threads ~{threads} \
      --minimap2-params "~{minimap2_params}" \
      --db-bacteria "~{db_bacteria}" \
      --db-fungi "~{db_fungi}" \
      --db-parasite "~{db_parasite}" \
      --db-virus "~{db_virus}" \
      --fasta-bacteria "~{fasta_bacteria}" \
      --fasta-fungi "~{fasta_fungi}" \
      --fasta-parasite "~{fasta_parasite}" \
      --fasta-virus "~{fasta_virus}" \
      --annot-pathogen "~{annot_pathogen}" \
      --annot-virus "~{annot_virus}"

    mkdir -p outputs
    cp -f "${OUT}/outputs/~{sample_id}_identification.tsv" outputs/identification.tsv
    cp -f "${OUT}/outputs/query_best_hits.tsv" outputs/query_best_hits.tsv
    cp -f "${OUT}/outputs/~{sample_id}_contig_report.tsv" outputs/contig_report.tsv
    cp -f "${OUT}/outputs/~{sample_id}_species_report.tsv" outputs/species_report.tsv

    mkdir -p outputs/paf
    if compgen -G "${OUT}/02_identification/paf/*.paf" > /dev/null; then
      cp -f "${OUT}/02_identification/paf/"*.paf outputs/paf/
    fi
  >>>

  output {
    File identification_tsv = "outputs/identification.tsv"
    File best_hits_tsv      = "outputs/query_best_hits.tsv"
    Array[File] paf_files   = glob("outputs/paf/*.paf")
    File contig_report_tsv  = "outputs/contig_report.tsv"
    File species_report_tsv = "outputs/species_report.tsv"
  }

  runtime {
    docker: docker_image
    cpu: cpu
    memory: "~{memory_gb} GB"
    disks: "local-disk ~{disk_gb} SSD"
  }
}


task Evaluate {
  input {
    String sample_id
    File   contigs_raw
    File   contigs_renamed
    File   best_hits
    File   identification_tsv
    File   read_support_tsv
    File? fasta_bacteria
    File? fasta_fungi
    File? fasta_parasite
    File? fasta_virus
    String work_base
    Int    threads
    Int    max_unique_references
    String metaquast_params
    String docker_image
    Int    cpu
    Int    memory_gb
    Int    disk_gb
  }

  command <<<
    set -euo pipefail
    OUT="~{work_base}/04_evaluate_work"
    mkdir -p "${OUT}"

    bash /app/scripts/run_evaluate.sh \
      --sample "~{sample_id}" \
      --contigs-raw "~{contigs_raw}" \
      --contigs-renamed "~{contigs_renamed}" \
      --best-hits "~{best_hits}" \
      --identification-tsv "~{identification_tsv}" \
      --read-support-tsv "~{read_support_tsv}" \
      --out-dir "${OUT}" \
      --threads ~{threads} \
      --max-unique-references ~{max_unique_references} \
      --metaquast-params "~{metaquast_params}" \
      --fasta-bacteria "~{fasta_bacteria}" \
      --fasta-fungi "~{fasta_fungi}" \
      --fasta-parasite "~{fasta_parasite}" \
      --fasta-virus "~{fasta_virus}"

    mkdir -p outputs
    cp -f "${OUT}/outputs/references.fa" outputs/references.fa
    cp -f "${OUT}/outputs/metaquast.tar.gz" outputs/metaquast.tar.gz
    cp -f "${OUT}/outputs/~{sample_id}_contig_report.tsv" outputs/contig_report.tsv
    cp -f "${OUT}/outputs/~{sample_id}_species_report.tsv" outputs/species_report.tsv
    cp -f "${OUT}/01_assembly/final.contigs.renamed.fa" outputs/final.contigs.renamed.fa
  >>>

  output {
    File final_contigs_renamed = "outputs/final.contigs.renamed.fa"
    File references_fa         = "outputs/references.fa"
    File metaquast_tar_gz      = "outputs/metaquast.tar.gz"
    File contig_report_tsv     = "outputs/contig_report.tsv"
    File species_report_tsv    = "outputs/species_report.tsv"
  }

  runtime {
    docker: docker_image
    cpu: cpu
    memory: "~{memory_gb} GB"
    disks: "local-disk ~{disk_gb} SSD"
  }
}

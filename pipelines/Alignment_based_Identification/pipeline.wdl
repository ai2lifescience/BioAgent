version 1.0

# =============================================================================
# Metagenomic Pathogen Detection Pipeline
#
# 病原体检测后半段；输入来自 stage0_qc.wdl，按 Stage 拆分为独立 WDL task：
#
#   Stage 1        : 病原体数据库比对（minimap2 + sambamba，4 类并行）
#   Stage 2        : 跨库仲裁（stage2_alignment_arbitrator.py）
#   Stage 3        : 物种注释（stage3_taxon_assigner.py）
#   Stage 4        : 基因组覆盖度指标（stage4_genome_metrics.py）
#   Stage 5        : 综合报告（stage5_report_builder.py）
#   Stage 6        : 可信度过滤（stage6_confidence_filter.py）
#
# 用法（Cromwell 示例）：
#   java -jar cromwell.jar run pipeline.wdl --inputs inputs.example.json
# =============================================================================

workflow MetagenomicDetection {
  input {
    # ── 样本信息 ─────────────────────────────────────────────────────────────
    String  sample_id
    String  project_id = ""
    String  user_id    = ""

    # ── Stage 0 输出（PE 双端 / SE 单端）────────────────────────────────────
    File    clean_r1
    File?   clean_r2
    Int?    post_host_reads

    # ── 病原体参考数据库（.mmi；未启用类型可不传，勿写 ""）────────────────
    String?  db_bacteria
    String?  db_virus
    String?  db_fungi
    String?  db_parasite

    # ── 注释文件 ──────────────────────────────────────────────────────────────
    String   anno_pathogen
    String   anno_virus
    String   non_report_list
    String?  white_list
    String?  posstat_file

    # ── 比对质量参数 ──────────────────────────────────────────────────────────
    Float maprate_bacteria  = 0.8
    Float maprate_virus     = 0.7
    Float maprate_fungi     = 0.8
    Float maprate_parasite  = 0.8
    Float misrate           = 0.1
    Int   min_as_score      = 30
    Int   min_mapq          = 20
    Float highpos_cutoff    = 0.05
    Float shannon_cut       = 3.0

    # ── Stage 6 参数 ──────────────────────────────────────────────────────────
    String stage6_lib_type             = "DNA"
    String stage6_product_type         = "DNA"
    Int    stage6_nonvir_topn          = 1000
    Int    stage6_fil_mrn              = 10
    Float  stage6_fil_shannon          = 0.75
    Float  stage6_fil_breadth          = 0.5
    Int    stage6_species_keep_limit   = 400

    # ── 物种特殊处理 ──────────────────────────────────────────────────────────
    String special_aspergillus_genus_ids  = "Aspergillus"
    String special_salmonella_species_ids = "Salmonella enterica subsp. enterica serovar Typhi,Salmonella enterica subsp. enterica serovar Typhimurium,Salmonella enterica"
    Int    special_min_smrn               = 3

    # ── 中间文件策略 ──────────────────────────────────────────────────────────
    Boolean keep_intermediate = false
    Boolean lean_io_mode      = true

    # ── 运行时资源（runtime 参数）──────────────────────────────────────────────
    String docker_image             # 镜像名称，如 mscan-detection:latest
    Int    cpu_map     = 8          # Stage 1 每个数据库映射任务 CPU
    Int    cpu_stage   = 4          # Stage 2–6 CPU
    Int    mem_map_gb  = 64         # Stage 1 内存 (GB)
    Int    mem_stage_gb = 16        # Stage 2–6 内存 (GB)
    Int    disk_gb     = 500        # 每个任务磁盘 (GB)
  }

  Boolean is_pe = defined(clean_r2)
  Boolean enable_bacteria = defined(db_bacteria)
  Boolean enable_virus    = defined(db_virus)
  Boolean enable_fungi    = defined(db_fungi)
  Boolean enable_parasite = defined(db_parasite)

  # ===========================================================================
  # Stage 1: 并行比对至各病原体数据库（条件调用）
  # ===========================================================================
  if (enable_bacteria && defined(db_bacteria)) {
    call MapToDatabase as MapBacteria {
      input:
        sample_id    = sample_id,
        db_type      = "bacteria",
        db_file      = select_first([db_bacteria]),
        clean_r1     = clean_r1,
        clean_r2     = clean_r2,
        is_pe        = is_pe,
        maprate      = maprate_bacteria,
        threads      = cpu_map,
        lean_io_mode = lean_io_mode,
        docker_image = docker_image,
        cpu          = cpu_map,
        memory_gb    = mem_map_gb,
        disk_gb      = disk_gb
    }
  }

  if (enable_virus && defined(db_virus)) {
    call MapToDatabase as MapVirus {
      input:
        sample_id    = sample_id,
        db_type      = "virus",
        db_file      = select_first([db_virus]),
        clean_r1     = clean_r1,
        clean_r2     = clean_r2,
        is_pe        = is_pe,
        maprate      = maprate_virus,
        threads      = cpu_map,
        lean_io_mode = lean_io_mode,
        docker_image = docker_image,
        cpu          = cpu_map,
        memory_gb    = mem_map_gb,
        disk_gb      = disk_gb
    }
  }

  if (enable_fungi && defined(db_fungi)) {
    call MapToDatabase as MapFungi {
      input:
        sample_id    = sample_id,
        db_type      = "fungi",
        db_file      = select_first([db_fungi]),
        clean_r1     = clean_r1,
        clean_r2     = clean_r2,
        is_pe        = is_pe,
        maprate      = maprate_fungi,
        threads      = cpu_map,
        lean_io_mode = lean_io_mode,
        docker_image = docker_image,
        cpu          = cpu_map,
        memory_gb    = mem_map_gb,
        disk_gb      = disk_gb
    }
  }

  if (enable_parasite && defined(db_parasite)) {
    call MapToDatabase as MapParasite {
      input:
        sample_id    = sample_id,
        db_type      = "parasite",
        db_file      = select_first([db_parasite]),
        clean_r1     = clean_r1,
        clean_r2     = clean_r2,
        is_pe        = is_pe,
        maprate      = maprate_parasite,
        threads      = cpu_map,
        lean_io_mode = lean_io_mode,
        docker_image = docker_image,
        cpu          = cpu_map,
        memory_gb    = mem_map_gb,
        disk_gb      = disk_gb
    }
  }

  # ===========================================================================
  # Stage 2: 跨库仲裁
  # ===========================================================================
  call Stage2Arbitration {
    input:
      sample_id        = sample_id,
      bam_bacteria     = MapBacteria.raw_bam,
      bam_virus        = MapVirus.raw_bam,
      bam_fungi        = MapFungi.raw_bam,
      bam_parasite     = MapParasite.raw_bam,
      enable_bacteria  = enable_bacteria,
      enable_virus     = enable_virus,
      enable_fungi     = enable_fungi,
      enable_parasite  = enable_parasite,
      maprate_bacteria = maprate_bacteria,
      maprate_virus    = maprate_virus,
      maprate_fungi    = maprate_fungi,
      maprate_parasite = maprate_parasite,
      misrate          = misrate,
      posstat_file     = posstat_file,
      highpos_cutoff   = highpos_cutoff,
      docker_image     = docker_image,
      cpu              = cpu_stage,
      memory_gb        = mem_stage_gb,
      disk_gb          = disk_gb
  }

  # ===========================================================================
  # Stage 3: 物种注释
  # ===========================================================================
  call Stage3Taxonomy {
    input:
      sample_id       = sample_id,
      bam_bacteria    = Stage2Arbitration.pass_bam_bacteria,
      bam_virus       = Stage2Arbitration.pass_bam_virus,
      bam_fungi       = Stage2Arbitration.pass_bam_fungi,
      bam_parasite    = Stage2Arbitration.pass_bam_parasite,
      enable_bacteria = enable_bacteria,
      enable_virus    = enable_virus,
      enable_fungi    = enable_fungi,
      enable_parasite = enable_parasite,
      min_as_score    = min_as_score,
      min_mapq        = min_mapq,
      anno_pathogen   = anno_pathogen,
      anno_virus      = anno_virus,
      docker_image    = docker_image,
      cpu             = cpu_stage,
      memory_gb       = mem_stage_gb,
      disk_gb         = disk_gb
  }

  # ===========================================================================
  # Stage 4: 基因组覆盖度指标
  # ===========================================================================
  call Stage4GenomeMetrics {
    input:
      sample_id       = sample_id,
      bam_bacteria    = Stage2Arbitration.pass_bam_bacteria,
      bam_virus       = Stage2Arbitration.pass_bam_virus,
      bam_fungi       = Stage2Arbitration.pass_bam_fungi,
      bam_parasite    = Stage2Arbitration.pass_bam_parasite,
      enable_bacteria = enable_bacteria,
      enable_virus    = enable_virus,
      enable_fungi    = enable_fungi,
      enable_parasite = enable_parasite,
      shannon_cut     = shannon_cut,
      anno_pathogen   = anno_pathogen,
      docker_image    = docker_image,
      cpu             = cpu_stage,
      memory_gb       = mem_stage_gb,
      disk_gb         = disk_gb
  }

  # ===========================================================================
  # Stage 5: 综合报告
  # ===========================================================================
  call Stage5Reporting {
    input:
      sample_id                      = sample_id,
      profile_bacteria               = Stage3Taxonomy.profile_bacteria,
      profile_virus                  = Stage3Taxonomy.profile_virus,
      profile_fungi                  = Stage3Taxonomy.profile_fungi,
      profile_parasite               = Stage3Taxonomy.profile_parasite,
      metrics_bacteria               = Stage4GenomeMetrics.metrics_bacteria,
      metrics_virus                  = Stage4GenomeMetrics.metrics_virus,
      metrics_fungi                  = Stage4GenomeMetrics.metrics_fungi,
      metrics_parasite               = Stage4GenomeMetrics.metrics_parasite,
      enable_bacteria                = enable_bacteria,
      enable_virus                   = enable_virus,
      enable_fungi                   = enable_fungi,
      enable_parasite                = enable_parasite,
      post_host_reads                = post_host_reads,
      clean_r1                       = clean_r1,
      stage2_read_accounting         = Stage2Arbitration.read_accounting,
      non_report_list                = non_report_list,
      special_aspergillus_genus_ids  = special_aspergillus_genus_ids,
      special_salmonella_species_ids = special_salmonella_species_ids,
      special_min_smrn               = special_min_smrn,
      docker_image                   = docker_image,
      cpu                            = cpu_stage,
      memory_gb                      = mem_stage_gb,
      disk_gb                        = disk_gb
  }

  # ===========================================================================
  # Stage 6: 可信度过滤（最终报告）
  # ===========================================================================
  call Stage6ConfidenceFilter {
    input:
      sample_id                 = sample_id,
      priority_panel            = Stage5Reporting.priority_panel,
      white_list                = white_list,
      non_report_list           = non_report_list,
      stage6_lib_type           = stage6_lib_type,
      stage6_product_type       = stage6_product_type,
      stage6_nonvir_topn        = stage6_nonvir_topn,
      stage6_fil_mrn            = stage6_fil_mrn,
      stage6_fil_shannon        = stage6_fil_shannon,
      stage6_fil_breadth        = stage6_fil_breadth,
      stage6_species_keep_limit = stage6_species_keep_limit,
      docker_image              = docker_image,
      cpu                       = cpu_stage,
      memory_gb                 = 8,
      disk_gb                   = 100
  }

  # ===========================================================================
  # Workflow outputs
  # ===========================================================================
  output {
    File   stage2_read_accounting       = Stage2Arbitration.read_accounting
    File   stage2_crossdb_signature     = Stage2Arbitration.crossdb_signature
    File   stage5_priority_panel        = Stage5Reporting.priority_panel
    File   sample_overview              = Stage5Reporting.sample_overview
    File   final_report_with_confidence = Stage6ConfidenceFilter.final_report
    File?  final_report_retained        = Stage6ConfidenceFilter.retained_report
    File?  final_report_filtered        = Stage6ConfidenceFilter.filtered_report
    File?  keep_species_list            = Stage6ConfidenceFilter.keep_species_list
    File?  keep_genus_list              = Stage6ConfidenceFilter.keep_genus_list
  }
}

# =============================================================================
# Task: Stage 1 — 单库比对（可复用 task，条件调用 4 次）
#   minimap2 比对 + sambamba 过滤
# =============================================================================
task MapToDatabase {
  input {
    String  sample_id
    String  db_type       # bacteria | virus | fungi | parasite
    File    db_file       # .mmi 参考数据库
    File    clean_r1      # PE R1 或 SE reads
    File?   clean_r2      # PE R2；SE 时不传
    Boolean is_pe
    Float   maprate
    Int     threads
    Boolean lean_io_mode
    String  docker_image
    Int     cpu
    Int     memory_gb
    Int     disk_gb
  }

  command <<<
    set -euo pipefail

    SAMPLE="~{sample_id}"
    DB_TYPE="~{db_type}"
    THREADS=~{threads}
    MAPRATE=~{maprate}
    OUT_BAM="${SAMPLE}.${DB_TYPE}.raw.bam"

    # 大型数据库（细菌/真菌/寄生虫）需要 --split-prefix 防止内存溢出
    case "$DB_TYPE" in
      bacteria|fungi|parasite)
        SPLIT_OPT="--split-prefix ${SAMPLE}_tmp_${DB_TYPE}"
        ;;
      *)
        SPLIT_OPT=""
        ;;
    esac

    CLEAN_R2="~{if defined(clean_r2) then select_first([clean_r2]) else ''}"
    if [ "~{is_pe}" = "true" ]; then
      READS=("~{clean_r1}" "$CLEAN_R2")
    else
      READS=("~{clean_r1}")
    fi

    if [ "~{lean_io_mode}" = "true" ]; then
      minimap2 -ax sr -t "$THREADS" -N 50 --secondary=yes \
        -p "$MAPRATE" -I 200G ${SPLIT_OPT} \
        "~{db_file}" "${READS[@]}" | \
      sambamba view -S -f bam \
        -F "not unmapped and not supplementary" \
        /dev/stdin -o "$OUT_BAM"
    else
      minimap2 -ax sr -t "$THREADS" -N 50 --secondary=yes \
        -p "$MAPRATE" -I 200G ${SPLIT_OPT} \
        "~{db_file}" "${READS[@]}" \
        2> "${SAMPLE}.${DB_TYPE}.map.log" | \
      sambamba view -S -f bam \
        -F "not unmapped and not supplementary" \
        /dev/stdin -o "$OUT_BAM" \
        2>> "${SAMPLE}.${DB_TYPE}.map.log"
    fi
  >>>

  output {
    File raw_bam = "~{sample_id}.~{db_type}.raw.bam"
  }

  runtime {
    docker: docker_image
    cpu:    cpu
    memory: "~{memory_gb} GB"
    disks:  "local-disk ~{disk_gb} SSD"
  }
}

# =============================================================================
# Task: Stage 2 — 跨库仲裁
# =============================================================================
task Stage2Arbitration {
  input {
    String  sample_id
    File?   bam_bacteria
    File?   bam_virus
    File?   bam_fungi
    File?   bam_parasite
    Boolean enable_bacteria
    Boolean enable_virus
    Boolean enable_fungi
    Boolean enable_parasite
    Float   maprate_bacteria
    Float   maprate_virus
    Float   maprate_fungi
    Float   maprate_parasite
    Float   misrate
    File?   posstat_file
    Float   highpos_cutoff
    String  docker_image
    Int     cpu
    Int     memory_gb
    Int     disk_gb
  }

  command <<<
    set -euo pipefail
    export PYTHONUNBUFFERED=1

    SAMPLE="~{sample_id}"

    # 通过环境变量将 WDL 插值传给 Python，避免 true/false 语法问题
    export ENABLE_BACTERIA="~{enable_bacteria}"
    export ENABLE_VIRUS="~{enable_virus}"
    export ENABLE_FUNGI="~{enable_fungi}"
    export ENABLE_PARASITE="~{enable_parasite}"
    export BAM_BACTERIA="~{if defined(bam_bacteria)  then select_first([bam_bacteria])  else ''}"
    export BAM_VIRUS="~{if defined(bam_virus)        then select_first([bam_virus])      else ''}"
    export BAM_FUNGI="~{if defined(bam_fungi)        then select_first([bam_fungi])      else ''}"
    export BAM_PARASITE="~{if defined(bam_parasite)  then select_first([bam_parasite])   else ''}"

    # CHECK_SIZE=0：Stage 2 的 raw BAM 由 MapToDatabase 直接产出，不含占位文件
    BAM_JSON=$(CHECK_SIZE=0 python3 /app/scripts/build_bam_json.py)

    export MISRATE="~{misrate}"
    export MAPRATE_BACTERIA="~{maprate_bacteria}"
    export MAPRATE_VIRUS="~{maprate_virus}"
    export MAPRATE_FUNGI="~{maprate_fungi}"
    export MAPRATE_PARASITE="~{maprate_parasite}"
    LIMITS_JSON=$(python3 /app/scripts/build_limits_json.py --stage 2)

    POSSTAT="~{if defined(posstat_file) then select_first([posstat_file]) else ''}"

    python3 /app/stage2_alignment_arbitrator.py \
      "$SAMPLE" "$LIMITS_JSON" "$BAM_JSON" "$POSSTAT" "~{highpos_cutoff}"

    # 生成缺失的占位文件（单库运行时部分文件可能不产出）
    for DB in bacteria virus fungi parasite; do
      F="${SAMPLE}.${DB}.stage2.pass.bam"
      [ -f "$F" ] || touch "$F"
    done
    [ -f "${SAMPLE}.stage2.read_accounting.tsv"   ] || printf 'db\treads\n' > "${SAMPLE}.stage2.read_accounting.tsv"
    [ -f "${SAMPLE}.stage2.crossdb_signature.tsv" ] || printf 'read_id\tdb\n' > "${SAMPLE}.stage2.crossdb_signature.tsv"
  >>>

  output {
    File  pass_bam_bacteria  = "~{sample_id}.bacteria.stage2.pass.bam"
    File  pass_bam_virus     = "~{sample_id}.virus.stage2.pass.bam"
    File  pass_bam_fungi     = "~{sample_id}.fungi.stage2.pass.bam"
    File  pass_bam_parasite  = "~{sample_id}.parasite.stage2.pass.bam"
    File  read_accounting    = "~{sample_id}.stage2.read_accounting.tsv"
    File  crossdb_signature  = "~{sample_id}.stage2.crossdb_signature.tsv"
  }

  runtime {
    docker: docker_image
    cpu:    cpu
    memory: "~{memory_gb} GB"
    disks:  "local-disk ~{disk_gb} SSD"
  }
}

# =============================================================================
# Task: Stage 3 — 物种注释（LCA 分类）
# =============================================================================
task Stage3Taxonomy {
  input {
    String  sample_id
    File    bam_bacteria    # stage2 pass BAM（空文件表示未启用）
    File    bam_virus
    File    bam_fungi
    File    bam_parasite
    Boolean enable_bacteria
    Boolean enable_virus
    Boolean enable_fungi
    Boolean enable_parasite
    Int     min_as_score
    Int     min_mapq
    File    anno_pathogen
    File    anno_virus
    String  docker_image
    Int     cpu
    Int     memory_gb
    Int     disk_gb
  }

  command <<<
    set -euo pipefail
    export PYTHONUNBUFFERED=1

    SAMPLE="~{sample_id}"

    export ENABLE_BACTERIA="~{enable_bacteria}"
    export ENABLE_VIRUS="~{enable_virus}"
    export ENABLE_FUNGI="~{enable_fungi}"
    export ENABLE_PARASITE="~{enable_parasite}"
    export BAM_BACTERIA="~{bam_bacteria}"
    export BAM_VIRUS="~{bam_virus}"
    export BAM_FUNGI="~{bam_fungi}"
    export BAM_PARASITE="~{bam_parasite}"

    BAM_JSON=$(python3 /app/scripts/build_bam_json.py)

    export MIN_AS_SCORE="~{min_as_score}"
    export MIN_MAPQ="~{min_mapq}"
    LIMITS_JSON=$(python3 /app/scripts/build_limits_json.py --stage 3)

    python3 /app/stage3_taxon_assigner.py \
      "$SAMPLE" "$LIMITS_JSON" "$BAM_JSON" \
      "~{anno_pathogen}" "~{anno_virus}"

    for DB in bacteria virus fungi parasite; do
      F="${SAMPLE}.${DB}.stage3.reference_profile.tsv"
      [ -f "$F" ] || touch "$F"
    done
  >>>

  output {
    File profile_bacteria = "~{sample_id}.bacteria.stage3.reference_profile.tsv"
    File profile_virus    = "~{sample_id}.virus.stage3.reference_profile.tsv"
    File profile_fungi    = "~{sample_id}.fungi.stage3.reference_profile.tsv"
    File profile_parasite = "~{sample_id}.parasite.stage3.reference_profile.tsv"
  }

  runtime {
    docker: docker_image
    cpu:    cpu
    memory: "~{memory_gb} GB"
    disks:  "local-disk ~{disk_gb} SSD"
  }
}

# =============================================================================
# Task: Stage 4 — 基因组覆盖度 & Shannon 熵
# =============================================================================
task Stage4GenomeMetrics {
  input {
    String  sample_id
    File    bam_bacteria
    File    bam_virus
    File    bam_fungi
    File    bam_parasite
    Boolean enable_bacteria
    Boolean enable_virus
    Boolean enable_fungi
    Boolean enable_parasite
    Float   shannon_cut
    File    anno_pathogen
    String  docker_image
    Int     cpu
    Int     memory_gb
    Int     disk_gb
  }

  command <<<
    set -euo pipefail
    export PYTHONUNBUFFERED=1

    SAMPLE="~{sample_id}"

    export ENABLE_BACTERIA="~{enable_bacteria}"
    export ENABLE_VIRUS="~{enable_virus}"
    export ENABLE_FUNGI="~{enable_fungi}"
    export ENABLE_PARASITE="~{enable_parasite}"
    export BAM_BACTERIA="~{bam_bacteria}"
    export BAM_VIRUS="~{bam_virus}"
    export BAM_FUNGI="~{bam_fungi}"
    export BAM_PARASITE="~{bam_parasite}"

    BAM_JSON=$(python3 /app/scripts/build_bam_json.py)

    python3 /app/stage4_genome_metrics.py \
      "$SAMPLE" "$BAM_JSON" "~{shannon_cut}" "~{anno_pathogen}"

    for DB in bacteria virus fungi parasite; do
      F="${SAMPLE}.${DB}.stage4.genome_metrics.tsv"
      [ -f "$F" ] || touch "$F"
    done
  >>>

  output {
    File metrics_bacteria = "~{sample_id}.bacteria.stage4.genome_metrics.tsv"
    File metrics_virus    = "~{sample_id}.virus.stage4.genome_metrics.tsv"
    File metrics_fungi    = "~{sample_id}.fungi.stage4.genome_metrics.tsv"
    File metrics_parasite = "~{sample_id}.parasite.stage4.genome_metrics.tsv"
  }

  runtime {
    docker: docker_image
    cpu:    cpu
    memory: "~{memory_gb} GB"
    disks:  "local-disk ~{disk_gb} SSD"
  }
}

# =============================================================================
# Task: Stage 5 — 综合报告（Priority Panel）
# =============================================================================
task Stage5Reporting {
  input {
    String  sample_id
    File    profile_bacteria
    File    profile_virus
    File    profile_fungi
    File    profile_parasite
    File    metrics_bacteria
    File    metrics_virus
    File    metrics_fungi
    File    metrics_parasite
    Boolean enable_bacteria
    Boolean enable_virus
    Boolean enable_fungi
    Boolean enable_parasite
    Int?    post_host_reads
    File    clean_r1
    File    stage2_read_accounting
    File    non_report_list
    String  special_aspergillus_genus_ids
    String  special_salmonella_species_ids
    Int     special_min_smrn
    String  docker_image
    Int     cpu
    Int     memory_gb
    Int     disk_gb
  }

  command <<<
    set -euo pipefail
    export PYTHONUNBUFFERED=1

    SAMPLE="~{sample_id}"

    POST_HOST_READS="~{if defined(post_host_reads) then select_first([post_host_reads]) else -1}"
    if [ "$POST_HOST_READS" -lt 0 ]; then
      POST_HOST_READS=$(python3 /app/scripts/count_reads.py "~{clean_r1}")
    fi

    export ENABLE_BACTERIA="~{enable_bacteria}"
    export ENABLE_VIRUS="~{enable_virus}"
    export ENABLE_FUNGI="~{enable_fungi}"
    export ENABLE_PARASITE="~{enable_parasite}"
    export PROFILE_BACTERIA="~{profile_bacteria}"
    export PROFILE_VIRUS="~{profile_virus}"
    export PROFILE_FUNGI="~{profile_fungi}"
    export PROFILE_PARASITE="~{profile_parasite}"
    export METRICS_BACTERIA="~{metrics_bacteria}"
    export METRICS_VIRUS="~{metrics_virus}"
    export METRICS_FUNGI="~{metrics_fungi}"
    export METRICS_PARASITE="~{metrics_parasite}"

    # build_profile_json.py 输出两行：第 1 行 anno JSON，第 2 行 cov JSON
    PROFILE_OUTPUT=$(python3 /app/scripts/build_profile_json.py)
    ANNO_JSON=$(echo "$PROFILE_OUTPUT" | sed -n '1p')
    COV_JSON=$(echo  "$PROFILE_OUTPUT" | sed -n '2p')

    python3 /app/stage5_report_builder.py \
      "$SAMPLE" "$ANNO_JSON" "$COV_JSON" "$POST_HOST_READS" \
      "" "~{non_report_list}" \
      "~{special_aspergillus_genus_ids}" \
      "~{special_salmonella_species_ids}" \
      "~{special_min_smrn}"

    # ── 生成 sample_overview ──────────────────────────────────────────────
    BAC=0; VIR=0; FUN=0; PAR=0
    ACC="~{stage2_read_accounting}"
    if [ -f "$ACC" ]; then
      BAC=$(awk -F'\t' '$1=="bacteria" {print $2; exit}' "$ACC"); BAC=${BAC:-0}
      VIR=$(awk -F'\t' '$1=="virus"    {print $2; exit}' "$ACC"); VIR=${VIR:-0}
      FUN=$(awk -F'\t' '$1=="fungi"    {print $2; exit}' "$ACC"); FUN=${FUN:-0}
      PAR=$(awk -F'\t' '$1=="parasite" {print $2; exit}' "$ACC"); PAR=${PAR:-0}
    fi
    MAPPED=$((BAC + VIR + FUN + PAR))
    {
      printf 'SampleId\tMappedMicrobeReads\tMappedBacteriaReads\tMappedFungiReads\tMappedParasiteReads\tMappedVirusReads\n'
      printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$SAMPLE" "$MAPPED" "$BAC" "$FUN" "$PAR" "$VIR"
    } > "${SAMPLE}.run.sample_overview.tsv"

    [ -f "${SAMPLE}.stage5.priority_microbe_panel.tsv" ] || touch "${SAMPLE}.stage5.priority_microbe_panel.tsv"
  >>>

  output {
    File priority_panel  = "~{sample_id}.stage5.priority_microbe_panel.tsv"
    File sample_overview = "~{sample_id}.run.sample_overview.tsv"
  }

  runtime {
    docker: docker_image
    cpu:    cpu
    memory: "~{memory_gb} GB"
    disks:  "local-disk ~{disk_gb} SSD"
  }
}

# =============================================================================
# Task: Stage 6 — 可信度过滤
# =============================================================================
task Stage6ConfidenceFilter {
  input {
    String  sample_id
    File    priority_panel
    File?   white_list
    File    non_report_list
    String  stage6_lib_type
    String  stage6_product_type
    Int     stage6_nonvir_topn
    Int     stage6_fil_mrn
    Float   stage6_fil_shannon
    Float   stage6_fil_breadth
    Int     stage6_species_keep_limit
    String  docker_image
    Int     cpu
    Int     memory_gb
    Int     disk_gb
  }

  command <<<
    set -euo pipefail
    export PYTHONUNBUFFERED=1

    SAMPLE="~{sample_id}"
    WHITE_LIST="~{if defined(white_list) then select_first([white_list]) else ''}"

    python3 /app/stage6_confidence_filter.py \
      "$SAMPLE" \
      "~{priority_panel}" \
      "$WHITE_LIST" \
      "~{non_report_list}" \
      "~{stage6_lib_type}" \
      "~{stage6_product_type}" \
      "~{stage6_nonvir_topn}" \
      "~{stage6_fil_mrn}" \
      "~{stage6_fil_shannon}" \
      "~{stage6_fil_breadth}" \
      "~{stage6_species_keep_limit}"

    # 生成占位文件保证输出声明可解析（文件名须与 output 声明完全一致）
    [ -f "${SAMPLE}.stage6.priority_with_confidence.tsv" ] || touch "${SAMPLE}.stage6.priority_with_confidence.tsv"
    [ -f "${SAMPLE}.stage6.priority_retained.tsv"        ] || touch "${SAMPLE}.stage6.priority_retained.tsv"
    [ -f "${SAMPLE}.stage6.priority_filtered.tsv"        ] || touch "${SAMPLE}.stage6.priority_filtered.tsv"
    [ -f "${SAMPLE}.stage6.keep_species.list"            ] || touch "${SAMPLE}.stage6.keep_species.list"
    [ -f "${SAMPLE}.stage6.keep_genus.list"              ] || touch "${SAMPLE}.stage6.keep_genus.list"
  >>>

  output {
    File  final_report      = "~{sample_id}.stage6.priority_with_confidence.tsv"
    File  retained_report   = "~{sample_id}.stage6.priority_retained.tsv"
    File  filtered_report   = "~{sample_id}.stage6.priority_filtered.tsv"
    File  keep_species_list = "~{sample_id}.stage6.keep_species.list"
    File  keep_genus_list   = "~{sample_id}.stage6.keep_genus.list"
  }

  runtime {
    docker: docker_image
    cpu:    cpu
    memory: "~{memory_gb} GB"
    disks:  "local-disk ~{disk_gb} SSD"
  }
}

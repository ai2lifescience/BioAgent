version 1.0

## ScreenMec — 生物序列安全筛选流水线
##
## 三步级联过滤:
##   Step 1: Bowtie2 比对 biorisk 数据库 → FLAG 高风险序列
##   Step 2: blastx 比对 UniRef100 + FunSoCs 毒力功能筛查 → FLAG 毒素相关序列
##   Step 3: blastn 比对 NT 数据库 + 病原体谱系识别 + 低关注度排除 → FLAG 病原体序列
##
## 提交 Cromwell:
##   java -jar cromwell.jar run screenmec.wdl \
##     --inputs inputs.example.json \
##     -Dconfig.screenmec/wdl/cromwell.example.conf
##
## 注意: String 数据库路径需在 Cromwell docker-options 中 bind mount 进容器;
##       传入 Bowtie2/BLAST 库前缀路径 (如 .../ScreenMec/biorisk), 非 ScreenMec 目录本身.
##
## Docker 镜像构建:
##   docker build -t cncb/screenmec:v1.0 -f Dockerfile .
##   (需要包含: bowtie2, blast+, python(3.9+), biopython, pandas, pytaxonkit,
##             以及 /app/run_pipeline.py 脚本)

workflow ScreenMec {
  input {
    # ============================================================
    # I/O
    # ============================================================
    File query_fasta
    String sample_id = ""
    Int threads = 40

    # ============================================================
    # 数据库
    #   - File: Cromwell 本地化到容器内
    #   - String: 容器内已挂载的路径 (biorisk_index, uniref_db, nt_db, taxonkit_data_dir, benign_fasta_db)
    # ============================================================
    # Bowtie2 索引前缀路径 (容器内已挂载, 如 .../biorisk)
    String biorisk_index

    # UniRef100 BLAST 蛋白数据库前缀路径 (容器内已挂载, 如 .../UNIREF100.mini)
    String uniref_db

    # FunSoCs 毒力功能数据库
    File funsocs_tsv
    File funsocs_pck

    # NT 核心 BLAST 数据库前缀路径 (容器内已挂载, 如 .../core_nt)
    String nt_db

    # 受管制 taxonomy ID 列表
    File regulated_taxids

    # TaxonKit 数据目录 (容器内已挂载, 如 .../taxonkit)
    String taxonkit_data_dir

    # 低关注度良性序列 BLAST 数据库前缀路径 (容器内已挂载, 如 .../benign.fasta)
    String benign_fasta_db

    # ============================================================
    # blastx 参数
    # ============================================================
    Float blastx_evalue = 0.0000000001
    Int blastx_max_target_seqs = 500

    # ============================================================
    # blastn 参数 (NT 数据库)
    # ============================================================
    Float blastn_evalue = 10
    Int blastn_max_target_seqs = 50
    Int blastn_culling_limit = 5

    # ============================================================
    # 低关注度排除参数
    # ============================================================
    Float low_concern_min_coverage = 0.8
    Float low_concern_max_evalue = 0.00001
    Float low_concern_min_identity = 90.0

    # ============================================================
    # 运行时资源
    # ============================================================
    String docker_image = "cncb/screenmec:v1.0"
    Int cpu = 40
    Int memory_gb = 64
    # staging core_nt 等大库需要足够本地盘
    Int disk_gb = 300
  }

  String sample = if (sample_id != "") then sample_id
                  else sub(basename(query_fasta), "\\.[^.]*$", "")

  call run_screenmec {
    input:
      query_fasta      = query_fasta,
      sample           = sample,
      threads          = threads,
      biorisk_index    = biorisk_index,
      uniref_db        = uniref_db,
      funsocs_tsv      = funsocs_tsv,
      funsocs_pck      = funsocs_pck,
      nt_db            = nt_db,
      regulated_taxids = regulated_taxids,
      taxonkit_data_dir = taxonkit_data_dir,
      benign_fasta_db  = benign_fasta_db,
      blastx_evalue    = blastx_evalue,
      blastx_max_target_seqs = blastx_max_target_seqs,
      blastn_evalue    = blastn_evalue,
      blastn_max_target_seqs = blastn_max_target_seqs,
      blastn_culling_limit   = blastn_culling_limit,
      low_concern_min_coverage = low_concern_min_coverage,
      low_concern_max_evalue   = low_concern_max_evalue,
      low_concern_min_identity = low_concern_min_identity,
      docker_image     = docker_image,
      cpu              = cpu,
      memory_gb        = memory_gb,
      disk_gb          = disk_gb
  }

  output {
    File result_tsv = run_screenmec.result_tsv
  }
}


task run_screenmec {
  input {
    File   query_fasta
    String sample
    Int    threads

    String biorisk_index
    String uniref_db
    File   funsocs_tsv
    File   funsocs_pck
    String nt_db
    File   regulated_taxids
    String taxonkit_data_dir
    String benign_fasta_db

    Float  blastx_evalue
    Int    blastx_max_target_seqs
    Float  blastn_evalue
    Int    blastn_max_target_seqs
    Int    blastn_culling_limit
    Float  low_concern_min_coverage
    Float  low_concern_max_evalue
    Float  low_concern_min_identity

    String docker_image
    Int    cpu
    Int    memory_gb
    Int    disk_gb
  }

  String result_file = sample + ".screenmec.tsv"

  command <<<
    set -euo pipefail

    echo "========================================"
    echo "ScreenMec Pipeline"
    echo "Sample: ~{sample}"
    echo "Threads: ~{threads}"
    echo "========================================"

    echo "=== [CHECK] /data mount ==="
    ls /data/ && echo "OK: /data mounted" || echo "FAIL: /data not mounted"
    ls ~{biorisk_index}* >/dev/null 2>&1 && echo "OK: biorisk files found" || echo "FAIL: biorisk files not found"
    echo "=============================="

    python3 /app/run_pipeline.py \
      --input           ~{query_fasta} \
      --output          "~{result_file}" \
      --threads         ~{threads} \
      --biorisk-index   ~{biorisk_index} \
      --uniref-db       ~{uniref_db} \
      --funsocs-tsv     ~{funsocs_tsv} \
      --funsocs-pck     ~{funsocs_pck} \
      --nt-db           ~{nt_db} \
      --regulated-taxids ~{regulated_taxids} \
      --taxonkit-data   ~{taxonkit_data_dir} \
      --benign-fasta    ~{benign_fasta_db} \
      --blastx-evalue           ~{blastx_evalue} \
      --blastx-max-target-seqs  ~{blastx_max_target_seqs} \
      --blastn-evalue           ~{blastn_evalue} \
      --blastn-max-target-seqs  ~{blastn_max_target_seqs} \
      --blastn-culling-limit    ~{blastn_culling_limit} \
      --low-concern-min-coverage  ~{low_concern_min_coverage} \
      --low-concern-max-evalue    ~{low_concern_max_evalue} \
      --low-concern-min-identity  ~{low_concern_min_identity}

    echo "========================================"
    echo "ScreenMec pipeline completed."
    echo "Result: ~{result_file}"
    echo "========================================"
  >>>

  output {
    File result_tsv = result_file
  }

  runtime {
    docker: docker_image
    cpu:    cpu
    memory: memory_gb + " GB"
    disks:  "local-disk " + disk_gb + " SSD"
  }
}

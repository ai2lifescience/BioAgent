# Bacterial biosynthetic gene clusters

这是 BacBGC WDL 的 Agent 包装目录，用于从细菌基因组 FASTA 或原始测序 reads 中识别生物合成基因簇（BGC）。Agent 使用统一的主输入文件槽位，并通过 `input_type` 选择输入模式。

## 输入

- `sequence_file1`：必填主输入文件；`input_type=genome` 时为组装基因组或 contig FASTA，`input_type=metagenome` 时为单端 FASTQ 或双端测序的 read 1；
- `sequence_file2`：可选的双端测序 read 2，仅在 `input_type=metagenome` 时使用；
- `input_type`：必填，可取 `genome` 或 `metagenome`。

使用 reads 时只提供 `sequence_file1` 也可以，工作流会按单端 reads 处理；提供 `sequence_file2` 时按双端 reads 处理。Agent 会将这两个文件分别映射到 `BacBGC.file1Path` 和 `BacBGC.file2Path`。

主要运行参数在 `runner.yaml` 的 `param_overrides` 中定义：`genome_context` 可取 `auto`、`complete` 或 `metagenome`，`bgc_backend` 可取 `auto`、`gecco` 或 `antismash`。`auto` 会根据 `input_type` 推断上下文，并在 complete 上下文选择 antiSMASH、在 metagenome 上下文选择 GECCO。

## 工作步骤

- 基因组模式：规范化 FASTA，按 `min_contig_length` 过滤 contig，然后运行 antiSMASH 或 GECCO；
- reads 模式：先用 fastp 做质控，再用 MEGAHIT 组装，之后执行同样的规范化和 BGC 检测；
- 结果解析由容器内的 `/opt/bacbgc/parse_bgc.py` 完成。

运行所需的容器镜像默认是 `cncb/bacbgc:v2`。线程数、内存和磁盘需求分别由 `threads`、`memory_gb` 和 `disk_gb` 控制。

## 输出

- `bgc_clusters.tsv`：检测到的 BGC cluster；
- `bgc_genes.tsv`：与 BGC 相关的基因；
- `bgc_features.tsv`：解析后的 BGC feature 注释。

## Cromwell / Agent 使用

使用 `pipeline_name: bacterial_bgc_detection`，上传一份主序列文件并设置 `input_type`；`genome` 模式上传 FASTA，`metagenome` 模式上传 read 1，并可选上传 read 2。`bacbgc.wdl` 保留原有的 fastp、MEGAHIT、规范化和 BGC 检测任务；`runner.yaml` 定义统一输入输出合同；`input.json` 只保留默认运行参数；`options.json` 配置 Cromwell 输出目录。本地另附演示数据 `data/input/bgc_demo_pao1.fasta`（PAO1 全基因组，约 6.3 MB），可用于 FASTA 模式测试。
# Bacterial defense system annotation

这是 BacDef WDL 的 Agent 包装目录，使用 DefenseFinder 识别细菌防御系统及其相关基因。Agent 使用统一的主输入文件槽位，并通过 `input_type` 选择输入模式。

## 输入

- `sequence_file1`：必填主输入文件；`input_type=genome` 时为组装基因组或 contig FASTA，`input_type=metagenome` 时为单端 FASTQ 或双端测序的 read 1；
- `sequence_file2`：可选的双端测序 read 2，仅在 `input_type=metagenome` 时使用；
- `input_type`：必填，可取 `genome` 或 `metagenome`。

使用 reads 时只提供 `sequence_file1` 也可以，工作流会按单端 reads 处理；提供 `sequence_file2` 时按双端 reads 处理。Agent 会将这两个文件分别映射到 `BacDef.file1Path` 和 `BacDef.file2Path`。

`defensefinder_models_dir` 是容器内可读的 DefenseFinder_compat 模型目录，默认值来自原始 BacDef 示例配置。该目录需要预先挂载到 Cromwell 任务容器中，不会随 pipeline 包复制。

## 工作步骤

- 基因组模式：规范化 FASTA，并按 `min_contig_length` 过滤 contig；
- reads 模式：先用 fastp 做质控，再用 MEGAHIT 组装，之后规范化 contig；
- 使用 Prodigal 预测蛋白、核酸和 GFF；
- 执行 `defense-finder run --db-type gembase`，再由容器内的 `/opt/bacdef/collect_tsv.py` 汇总结果；
- `genome_context=complete` 使用 Prodigal 的 `single` 模式，`metagenome` 使用 `meta` 模式；默认 `auto` 会根据 `input_type` 推断上下文。

默认容器镜像是 `cncb/bacdef:v2`。线程数、内存和磁盘需求分别由 `threads`、`memory_gb` 和 `disk_gb` 控制。

## 输出

- `defense_systems.tsv`：检测到的细菌防御系统；
- `defense_genes.tsv`：与防御系统相关的基因；
- `defense_hmmer_hits.tsv`：DefenseFinder 产生的 HMMER 命中结果。

## Cromwell / Agent 使用

使用 `pipeline_name: bacterial_defense_finder`，上传一份主序列文件并设置 `input_type`；`genome` 模式上传 FASTA，`metagenome` 模式上传 read 1，并可选上传 read 2。还需确保 `defensefinder_models_dir` 在任务容器中可读。

`workflow.wdl` 保留原有的 fastp、MEGAHIT、DefenseFinder 和结果汇总任务；`runner.yaml` 定义统一输入输出合同；`inputs.json` 保留默认运行参数；`options.json` 配置 Cromwell 输出目录。
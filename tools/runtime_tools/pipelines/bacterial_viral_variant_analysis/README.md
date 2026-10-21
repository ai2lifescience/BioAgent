# Bacterial and viral variant analysis

这是 `mutation_analysis.wdl` 的 Agent 包装目录，适用于单个细菌或病毒样本的 SNP/变异分析。流程同时支持宏基因组 FASTQ 和已经组装好的基因组 FASTA：

- `metagenome + bacteria`：细菌宏基因组 reads；
- `metagenome + virus`：病毒宏基因组 reads；
- `genome + bacteria`：细菌组装 FASTA；
- `genome + virus`：病毒组装 FASTA。

每次运行只处理一个样本，流程显式使用 `--skip-tree`，不构建多样本系统发育树。

## 输入

- `sequence_file1`：必填的 FASTQ/FASTQ.GZ R1（宏基因组模式）或单个组装 FASTA（基因组模式）；
- `sequence_file2`：可选的 FASTQ/FASTQ.GZ R2，只能用于宏基因组模式；基因组模式必须省略；
- `input_type`：必填，选择 `metagenome` 或 `genome`；
- `organism`：必填，选择 `bacteria` 或 `virus`；
- `reference_fasta`：可选的本地参考 FASTA；
- `species`、`taxonid`、`reference_accession`：可选的物种、分类 ID 或数据库 accession，用于从配置的资源中选择参考；具体组合应与细菌或病毒数据库一致；
- 细菌数据库：`gtdb_db_path` 和 `gtdb_metadata_path`；
- 病毒数据库：`virus_db_path` 和 `virus_metadata_path`；
- `threads`、覆盖度阈值、滑动窗口、步长、标准差阈值和 `aligner`：可通过 runner 参数覆盖。

`file1Path` 和 `file2Path` 在 WDL 中始终是文件，不接受目录。工作流会根据输入类型和文件后缀把文件暂存为统一的单样本输入；组装基因组不能同时提供 R2。

## 工作步骤和输出

任务容器内的 `/app/unified_runner.py` 根据 `input_type` 和 `organism` 选择对应的 mutation 分析实现，使用本地参考或配置的数据库执行比对、覆盖度过滤和变异整理。WDL 随后把结果整理到三个稳定输出：

- `snp_matrix`：SNP 矩阵；若工具产生的是 `filtered_snp_matrix.fasta`，则输出该 FASTA 比对文件；
- `variants.tsv`：变异明细表；
- `variants_summary.txt`：变异分析摘要。若底层工具没有生成明细或摘要，流程会创建空的对应文件，以保持输出合同稳定。

流程不会执行通用 reads 质控、组装、分子分型、临床风险评估或系统发育树构建。需要这些步骤时，应先运行相应的上游或专用 pipeline。

## Cromwell 部署要求

任务镜像默认为 `cncb/snp-mutation:v1.0`，并且必须包含 `/app/unified_runner.py` 及其依赖的 mutation 分析工具。`inputs.json` 中的 GTDB、病毒参考库和元数据路径是 Cromwell 任务主机及任务容器可读取的 Linux 路径，不是本机 Windows 路径；这些数据库不会随本包复制或上传。

FASTQ 或组装 FASTA 由 Agent 的输入存储配置上传或映射到 Cromwell。启动 Agent 前需要挂载相应数据库，配置 `CROMWELL_URL` 以及项目要求的输入/输出对象存储设置，并确保容器可以读取所有 WDL `File` 输入。

## 运行方式

从本目录复制输入模板，填写样本文件和所需模式参数后提交 Cromwell：

```bash
cp inputs.json inputs.local.json
# 添加 MutationAnalysis.input_type、MutationAnalysis.organism、
# MutationAnalysis.file1Path，以及宏基因组模式所需的 file2Path（可选）。
java -jar cromwell.jar run workflow.wdl -i inputs.local.json -o options.json
```

BioAgent 在未设置 `CROMWELL_URL` 时可使用本地 miniwdl；设置该变量后会通过 Cromwell REST 接口提交、轮询并收集上述三个声明输出。

## 文件说明

- `workflow.wdl`：统一封装四种输入/病原体组合的 WDL 工作流；
- `runner.yaml`：Agent 的输入文件、模式参数、部署资源和输出合同；
- `inputs.json`：GTDB/病毒数据库、镜像、线程和资源默认值；数据库路径需要按部署环境替换；
- `options.json`：Cromwell 输出选项；
- `data/input/`：小型细菌 reads/参考和 phiX174 病毒序列示例，不代替生产数据库，也不会自动覆盖 `inputs.json`。

结果依赖参考序列、数据库版本、输入序列质量和过滤阈值，属于变异分析证据，不等同于临床诊断。

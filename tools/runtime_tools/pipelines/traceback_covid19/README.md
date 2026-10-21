# COVID-19 Traceback

这是 `similar_sequence` WDL 的 Agent 包装目录，适用于将一个 query FASTA 与配置的参考 FASTA 做比对、基因型距离分析和树构建。

## 输入

- `query_fasta`：必填的 query 共识或组装 FASTA；
- `reference_fasta`：参考 FASTA，默认使用 `inputs.json` 中配置的 SARS-CoV-2 参考；
- `d_method`：基因型距离方法，默认 `WM`；
- Valkyrie 文件数组和 `indel_info`：由部署参数提供；
- `output_name_prefix`、`mafft_threads` 和 Docker 镜像：可通过 runner 参数覆盖。

## 工作步骤和输出

工作流依次执行参考与 query 拼接、MAFFT 多序列比对、突变列表生成、Valkyrie 基因型距离计算、SNP 序列生成和 FastTree 建树。输出为：

- 拼接后的 FASTA；
- MAFFT 比对结果；
- 两个突变列表结果；
- 基因型距离排名 TSV；
- SNP 序列 FASTA；
- FastTree Newick 树文件。

## Cromwell 部署要求

任务镜像默认为 `cncb/genome_tracing:v1.0`。`reference_fasta`、`valkyrie_files` 和 `indel_info` 的默认值是 Cromwell 任务主机及任务容器可读取的 Linux 路径，不是本机 Windows 路径；这些资源不会随本包复制或上传。启动 Agent 前需要挂载相应资源，并配置 `CROMWELL_URL` 及项目要求的输入/输出对象存储设置。

## 文件说明

- `workflow.wdl`：从 `wdl2agent/similar_sequence/SimilarSequence.wdl` 复制的 WDL 工作流（仅修正 `run_mafft` 中软链接变量名 `combined_fasta` → `combined_fa`）；
- `runner.yaml`：Agent 的 FASTA 输入、方法参数、部署资源和输出合同；
- `inputs.json`：沿用原 `input.json` 的参考库、Valkyrie、indel 和运行参数默认值，query FASTA 指向内置演示数据；
- `options.json`：Cromwell 输出选项；
- `data/input/similar_sequence_demo.fasta`：内置的演示 query 序列（SARS-CoV-2 全基因组 QB150279.1，来自 NCBI GenBank）。

结果依赖参考序列、Valkyrie 数据、输入序列质量和运行参数，属于分析结果，不等同于临床诊断。

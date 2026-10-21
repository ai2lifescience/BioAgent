# PHI-base genome annotation

这是 `PhiAnnotatorGenome` WDL 的 Agent 包装目录，适用于已经组装好的基因组 FASTA 或已经预测好的蛋白 FASTA。

## 输入

- `genome_fasta`：可选的组装核酸 FASTA；
- `protein_fasta`：可选的蛋白 FASTA。

两者必须提供其中一个，不能同时提供。提供基因组 FASTA 时，工作流先运行 Prodigal 预测 ORF，再使用 DIAMOND blastp；提供蛋白 FASTA 时直接进行 DIAMOND blastp。

PHI-base DIAMOND 数据库和 metadata 表通过 `inputs.json` 中的挂载路径提供：

- `PhiAnnotatorGenome.diamond_db`；
- `PhiAnnotatorGenome.metadata`。

这些路径必须同时存在于 Cromwell 任务容器内。数据库不会随 pipeline 包复制或上传。

## 工作步骤和输出

工作流调用容器中的 `/opt/phi-annotator-v2/workflow.py`，生成：

- `phi_hits.tsv`：命中明细；
- `phi_summary.tsv`：汇总结果；
- `qc.json`、`status.json`、`manifest.json`；
- `report.md`：Markdown 报告。

## Cromwell / Agent 使用

使用 `pipeline_name: phi_annotator_genome`，上传 `genome_fasta` 或 `protein_fasta`。启动 Agent 前需要保证任务镜像 `cncb/phi-annotator:v1.0`、PHI-base 数据库、metadata 文件和 `pipeline_dir` 在任务容器中可读。

`workflow.wdl` 从 `wdl2agent_complement/mscan-wdl/annotator/phi/phi_annotator_genome.wdl` 原样复制。 `runner.yaml` 定义 Agent 输入和输出合同，`inputs.json` 保留原 pipeline 的数据库和运行参数，`options.json` 配置 Cromwell 输出目录。




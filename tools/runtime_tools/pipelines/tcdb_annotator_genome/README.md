# TCDB genome annotation

这是 TcdbAnnotatorGenome WDL 的 Agent 包装目录，适用于已经组装好的基因组 FASTA 或已经预测好的蛋白 FASTA。

## 输入

- genome_fasta：可选的组装核酸 FASTA；
- protein_fasta：可选的蛋白 FASTA。

两者必须提供其中一个，不能同时提供。提供基因组 FASTA 时，工作流先运行 Prodigal 预测 ORF，再使用 BLASTP 或 DIAMOND；提供蛋白 FASTA 时直接进行蛋白比对。

数据库和 metadata 表通过 inputs.json 中的挂载路径提供：

- TcdbAnnotatorGenome.blast_db；
- TcdbAnnotatorGenome.diamond_db；
- TcdbAnnotatorGenome.metadata。

backend 默认是 blast，也可以切换为 diamond。tm_prediction 默认关闭；启用 TMbed 时需要提供对应的模型目录。上述数据库、模型目录和 pipeline_dir 必须同时存在于 Cromwell 任务容器内，不会随 pipeline 包复制或上传。

## 工作步骤和输出

工作流调用容器中的 /opt/tcdb-annotator-v2/workflow.py，生成：

- tcdb_hits.tsv：命中明细；
- tcdb_summary.tsv：汇总结果；
- tm_predictions.tsv：跨膜预测结果；
- qc.json、status.json、manifest.json；
- report.md：Markdown 报告。

## Cromwell / Agent 使用

使用 pipeline_name: tcdb_annotator_genome，上传 genome_fasta 或 protein_fasta。需要根据 backend 准备可读的 TCDB BLAST/DIAMOND 数据库。genome_context 会传给基因组输入模式，用于区分完整基因组和其他 contig 集合。

workflow.wdl 从 wdl2agent_complement/mscan-wdl/annotator/tcdb/tcdb_annotator_genome.wdl 原样复制。runner.yaml 定义 Agent 输入和输出合同，inputs.json 保留原 pipeline 的数据库和运行参数，options.json 配置 Cromwell 输出目录。


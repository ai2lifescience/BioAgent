# PHI-base metagenome read annotation

这是 `PhiAnnotatorMetagenome` WDL 的 Agent 包装目录，适用于单端或双端宏基因组 FASTQ reads 的 PHI-base 注释。

## 输入

- `read1`：必填的 R1 FASTQ/FASTQ.GZ；
- `read2`：可选的第二个 FASTQ；
- PHI-base DIAMOND 数据库和 metadata 表：由 `inputs.json` 中的挂载路径提供。

工作流直接使用 DIAMOND blastx 扫描 reads，不执行上游质控，也不组装。`read2` 会作为第二个 FASTQ 一起检索，WDL 不将两条 reads 组成真正的 PE 配对分析。

## 工作步骤和输出

工作流调用容器中的 `/opt/phi-annotator-v2/workflow.py`，生成：

- `phi_hits.tsv`：汇总命中；
- `phi_read_hits.tsv`：read-level 命中；
- `phi_summary.tsv`：汇总结果；
- `qc.json`、`status.json`、`manifest.json`；
- `report.md`：Markdown 报告。

## Cromwell / Agent 使用

使用 `pipeline_name: phi_annotator_metagenome`，上传必填的 `read1`，并按需上传 `read2`。启动 Agent 前需要保证任务镜像 `cncb/phi-annotator:v1.0`、PHI-base DIAMOND 数据库、metadata 文件和 `pipeline_dir` 在任务容器中可读。数据库不会随 pipeline 包复制或上传。

`workflow.wdl` 从 `wdl2agent_complement/mscan-wdl/annotator/phi/phi_annotator_metagenome.wdl` 原样复制。 `runner.yaml` 定义 Agent 输入和输出合同，`inputs.json` 保留原 pipeline 的数据库和运行参数，`options.json` 配置 Cromwell 输出目录。




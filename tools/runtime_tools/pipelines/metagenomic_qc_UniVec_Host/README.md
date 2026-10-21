# Metagenomic qc UniVec Host

这是 `ReadQc` WDL 的 Agent 包装目录，适用于宏基因组单端或双端 FASTQ reads 的接头、宿主和 UniVec 过滤。

## 输入

- `read1`：必填的 R1 FASTQ/FASTQ.GZ 文件；
- `read2`：可选的双端 R2 FASTQ/FASTQ.GZ 文件；
- `host_fasta`：可选的自定义宿主 FASTA。使用它时应清空 `host_name`；
- `sample_id`、接头序列、宿主名称、过滤开关和运行参数：由 runner 参数提供。

## 工作步骤和输出

工作流会根据输入是否包含 R2 选择单端或双端路径，依次执行：

1. FASTQ 格式归一化和 FastQC；
2. cutadapt 接头去除；
3. Trimmomatic 滑窗、首尾质量和最短长度过滤；
4. 可选的 UniVec Bowtie2 去除；
5. 可选的宿主 Bowtie2 去除；
6. 生成 QC 汇总表和 MultiQC HTML 报告。

输出包括清洗后的 R1/R2（单端时没有 R2）、`qc_summary.tsv` 和 `multiqc_report.html`。

## Cromwell 部署要求

任务镜像默认为 `cncb/qc-pipeline:v1.0`。`host_index_root` 和 `univec_index_prefix` 必须是 Cromwell 任务主机及任务容器可读取的 Linux 路径；数据库和索引不会随本包复制或上传。启动 Agent 前需要挂载这些资源，并配置 `CROMWELL_URL` 及项目要求的输入/输出对象存储设置。

当 `remove_host=true` 时，工作流要求提供 `host_name` 或 `host_fasta` 其中之一，不能同时提供。使用预置宿主时，`host_name` 必须对应 `host_index_root` 下的 Bowtie2 索引目录。

## 文件说明

- `workflow.wdl`：从 `wdl2agent_complement/mscan-wdl/mngs_pipeline/qc_pipeline.wdl` 原样复制的 WDL 工作流；
- `runner.yaml`：Agent 的 FASTQ/宿主 FASTA 输入、参数和输出合同；
- `inputs.json`：沿用 `inputs.pe.json` 的公共默认参数，不硬编码具体 FASTQ 文件；
- `options.json`：Cromwell 输出选项。

清洗结果依赖输入 reads、接头配置、宿主/UniVec 数据库版本和运行参数，不等同于病原体识别或临床诊断。

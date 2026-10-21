# Metagenomic pathogen identification based marker

这是 `StrainMeta` WDL 的 Agent 包装目录，适用于单端或双端宏基因组 FASTQ 的 MetaPhlAn 样本分析。

## 输入

- `read1`：必填的 R1 FASTQ/FASTQ.GZ 文件；
- `read2`：可选的双端 R2 FASTQ/FASTQ.GZ 文件；
- `sample_id`：样本名称，默认是 `SAMPLE`；
- `data_type`、MetaPhlAn 数据库目录和数据库索引：由 runner 参数提供。

工作流不会执行接头去除、质量控制、宿主过滤或组装。需要这些步骤时，应先运行相应的上游 pipeline。

## 工作步骤和输出

工作流调用容器内的 `run_metaphlan_sample.sh`，根据是否提供 R2 选择单端或双端分析，并生成：

- MetaPhlAn profile 文本表；
- 压缩 SAM 比对文件；
- consensus marker 压缩文件。

## Cromwell 部署要求

任务镜像默认为 `cncb/strain-meta:v1.0`。`metaphlan_db_dir` 必须是 Cromwell 任务主机及任务容器可读取的 Linux 目录，且其中必须存在由 `metaphlan_db_index` 指定的 `.pkl` 数据库文件。数据库不会随本包复制或上传。启动 Agent 前需要挂载数据库目录，并配置 `CROMWELL_URL` 及项目要求的输入/输出对象存储设置。

## 文件说明

- `workflow.wdl`：从 `wdl2agent/strain-meta/strain_meta.wdl` 原样复制的 WDL 工作流；
- `runner.yaml`：Agent 的 FASTQ 输入、MetaPhlAn 参数和三个输出合同；
- `inputs.json`：沿用原 `input.json` 的数据库、镜像和资源默认值，不硬编码具体 FASTQ 文件；
- `options.json`：Cromwell 输出选项。

结果依赖输入 reads、MetaPhlAn 数据库版本和运行参数，属于分析结果，不等同于临床诊断。

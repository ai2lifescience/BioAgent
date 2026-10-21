# Metagenomic pathogen identification based kmer

这是 `StrobeTaxaDetection` WDL 的 Agent 包装目录，适用于已经完成清洗的宏基因组 FASTQ reads。

## 输入

- `clean_r1`：必填的 R1 FASTQ/FASTQ.GZ 文件；
- `clean_r2`：可选的双端 R2 FASTQ/FASTQ.GZ 文件；
- `sample_id`：样本名称，默认是 `SAMPLE`；
- `db_dir`：StrobeTaxa 数据库目录，默认是 `/data/jiangxq39/strobetaxa/nt25_c16k8`；
- `feat3_threshold`、`bp_per_block`、`memmap`：分类参数；
- `docker_image`、`cpu`、`memory_gb`、`disk_gb`：任务运行参数。

工作流不会执行 reads 质控或接头清除；输入应当已经是清洗后的 reads。

## 工作步骤和输出

工作流先检查 StrobeTaxa 数据库，再合并单端或双端 reads，最后调用 `strobe_taxa.cli classify` 进行 k-mer/strobemer 分类。输出为：

- 分类结果 TSV；
- 分类报告 TSV；
- signature coverage CSV。

## Cromwell 部署要求

任务镜像默认为 `cncb/strobe-taxa:v1.0`。`db_dir` 必须是 Cromwell 任务主机和任务容器都能读取的 Linux 目录；数据库不会随本包复制或上传。若数据库位于共享挂载目录，需要在 `cromwell.conf` 中挂载其父路径。

启动 Agent 前需要配置 `CROMWELL_URL`，以及项目部署要求的输入/输出对象存储设置。

## 文件说明

- `workflow.wdl`：从 `wdl2agent/kmer-detection/pipeline.wdl` 原样复制的 WDL 工作流；
- `runner.yaml`：Agent 的 reads 输入、参数和三个输出合同；
- `inputs.json`：不固定具体 reads 文件的公共默认参数；
- `options.json`：Cromwell 输出选项。

结果依赖数据库版本、输入 reads 质量和运行参数，属于分析结果，不等同于临床诊断。

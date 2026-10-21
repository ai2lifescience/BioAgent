# Metagenomic growth rate calculation

这是 `StrainCoPTR` WDL 的 Agent 包装目录，适用于单端或双端宏基因组 FASTQ 的 CoPTR 生长速度分析。

## 输入

- `read1`：必填的 R1 FASTQ/FASTQ.GZ 文件；
- `read2`：可选的双端 R2 FASTQ/FASTQ.GZ 文件；
- `sample_id`：样本名称，默认是 `SAMPLE`；
- `min_reads`、线程数和运行资源：由 runner 参数提供。

工作流不会执行接头去除、质量控制、宿主过滤或组装。需要这些步骤时，应先运行相应的上游 pipeline。

## 工作步骤和输出

工作流调用容器内的 `run_coptr_sample.sh`，根据是否提供 R2 选择单端或双端分析，使用 CoPTR 参考基因组和索引估计基因组的 replication rate。输出为：

- `coptr_log2ptr.csv`：genome × sample 的 log2(PTR) 结果表。

## Cromwell 部署要求

任务镜像默认为 `cncb/strain-coptr:v1.0`。`coptr_ref_dir` 和 `coptr_index_dir` 必须是 Cromwell 任务主机及任务容器可读取的 Linux 路径；若索引已经存在，流程会复用它，否则会在任务工作目录中建立。参考基因组和索引不会随本包复制或上传。启动 Agent 前需要挂载这些目录，并配置 `CROMWELL_URL` 及项目要求的输入/输出对象存储设置。

## 文件说明

- `workflow.wdl`：从 `wdl2agent/strain-coptr/strain_coptr.wdl` 原样复制的 WDL 工作流；
- `runner.yaml`：Agent 的 FASTQ 输入、CoPTR 参数和输出合同；
- `inputs.json`：沿用原 `input.json` 的数据库、镜像和资源默认值，不硬编码具体 FASTQ 文件；
- `options.json`：Cromwell 输出选项。

结果依赖输入 reads、参考基因组、CoPTR 索引和最小 reads 阈值，属于分析结果，不等同于临床诊断。

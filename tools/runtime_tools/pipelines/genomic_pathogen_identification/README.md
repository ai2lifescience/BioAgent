# Genomic pathogen identification

这是 `MashIdentify` WDL 的 Agent 包装目录，适用于已经组装好或已经生成共识的核酸 FASTA。

## 输入

- `query_fasta`：必填的组装或共识 FASTA 文件；
- `sample_id`：样本名称，默认是 `SAMPLE`；
- Mash 数据库、病毒分类注释表和病原体注释表：由部署参数提供。

工作流不接收 FASTQ，也不执行 reads 质控、组装或变异风险评估。

## 工作步骤和输出

工作流为 query FASTA 生成三种 Mash sketch，分别与细菌、真菌、寄生虫和病毒数据库计算距离，然后调用容器内的 `mash_identify.py` 结合注释表进行整理。输出为：

- 样本级识别汇总 TSV；
- contig 级识别结果 TSV；
- 带注释的命中结果 TSV；
- 四个数据库对应的 Mash distance TSV 文件。

## Cromwell 部署要求

任务镜像默认为 `cncb/mash-identify:v1.0`。`runner.yaml` 中的数据库和注释路径是 Cromwell 任务主机及任务容器可读取的 Linux 路径，不是本机 Windows 路径；这些文件不会随本包复制或上传。启动 Agent 前需要在部署环境中挂载相应目录，并配置 `CROMWELL_URL` 及项目要求的输入/输出对象存储设置。

## 文件说明

- `workflow.wdl`：从 `wdl2agent/mash-identify/MashIdentify.wdl` 原样复制的 WDL 工作流；
- `runner.yaml`：Agent 的 FASTA 输入、部署资源参数和输出合同；
- `inputs.json`：沿用原流程的数据库、注释和运行参数默认值；
- `options.json`：Cromwell 输出选项。

结果依赖数据库版本、注释版本、输入 FASTA 质量和运行参数，属于分析结果，不等同于临床诊断。

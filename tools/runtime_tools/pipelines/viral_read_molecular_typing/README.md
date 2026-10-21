# Viral read molecular typing

这是新版 `molecular_typing_meta.wdl` 的 Pipeline2Agent 包装目录，适用于原始病毒测序 reads。

## 输入

- `read1`：必填的 FASTQ/FASTQ.GZ 文件；
- `read2`：可选的双端测序 R2 文件；
- `pathogen`：必须选择 `H1N1`、`H3N2` 或 `SARS_CoV_2`；
- `sample`：样本名称，可由 Agent 参数覆盖。

选择病原体时，`runner.yaml` 会同时切换该病原体对应的参考序列、BWA 索引、Nextclade 数据集和参考片段名称。不要只修改 pathogen 而保留另一种病原体的数据库。

## 工作步骤和输出

工作流执行 `fastp -> BWA -> BAM 过滤/去重复/trim -> iVar/Nextclade`，输出分型 CSV、Nextclade TSV/JSON、共识 FASTA 和最终 BAM。

## Cromwell 部署要求

本包面向服务器上的 Cromwell。任务镜像默认为 `cncb/molecular-wdl:v1.0`。`runner.yaml` 中的 `/data/zhaomh39/program/database/molecular_database/...` 是 Cromwell 任务主机可见的 Linux 路径，不是本机 Windows 路径；服务器和任务容器必须能读取这些参考文件。

FASTQ 由 Agent 的输入存储配置上传或映射到 Cromwell。启动 Agent 前需要配置 `CROMWELL_URL`，以及项目部署要求的输入/输出对象存储设置。

## 文件说明

- `workflow.wdl`：从新版 `molecular_typing_meta.wdl` 复制的 WDL 工作流；
- `runner.yaml`：Agent 的输入、参数、三病原 presets 和输出合同；
- `inputs.json`：公共默认参数，不在这里硬编码某一个病原体的参考库；
- `options.json`：Cromwell 输出选项；
- `data/`：本包不捆绑大型参考数据库，示例说明见 `data/README.md`。

结果是参考和阈值依赖的分析证据，不等同于临床诊断。

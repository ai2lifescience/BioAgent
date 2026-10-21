# Viral genome molecular typing

这是新版 `molecular_typing_genomic.wdl` 的 Pipeline2Agent 包装目录，适用于已经组装好或已经生成共识的病毒 FASTA。

## 输入

- `genome_fasta`：必填的 FASTA/FA/FNA 文件；
- `pathogen`：必须选择 `H1N1`、`H3N2` 或 `SARS_CoV_2`；
- `sample`：样本名称，可由 Agent 参数覆盖。

本包不接收 FASTQ，也不会执行 FASTQ 质控或 reads 比对。原始测序 reads 应使用 `viral_read_molecular_typing`。

## 工作步骤和输出

工作流执行 FASTA 整理、参考比对/提取、Nextclade 和汇总，输出分型 CSV、Nextclade TSV/JSON 和用于分型的 FASTA。这个 genomic 工作流没有最终 BAM 输出，因此不能复用 read 流程的 BAM 输出声明。

## Cromwell 部署要求

任务镜像默认为 `cncb/molecular-wdl:v1.0`。`runner.yaml` 中的 `/data/zhaomh39/program/database/molecular_database/...` 是 Cromwell 任务主机可见的 Linux 路径，不是本机 Windows 路径；服务器和任务容器必须能读取这些参考文件。

FASTA 由 Agent 的输入存储配置上传或映射到 Cromwell。启动 Agent 前需要配置 `CROMWELL_URL`，以及项目部署要求的输入/输出对象存储设置。

## 文件说明

- `workflow.wdl`：从新版 `molecular_typing_genomic.wdl` 复制的 WDL 工作流；
- `runner.yaml`：Agent 的输入、参数、三病原 presets 和输出合同；
- `inputs.json`：公共默认参数，不在这里硬编码某一个病原体的参考库；
- `options.json`：Cromwell 输出选项；
- `data/`：本包不捆绑大型参考数据库，示例说明见 `data/README.md`。

结果是参考和序列完整度依赖的分析证据，不等同于临床诊断。

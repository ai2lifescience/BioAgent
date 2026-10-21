# Pathogen consensus variant risk assessment

这是 `consensus-risk` WDL 的 Agent 包装目录，适用于已经生成好的病原体 consensus FASTA。

## 输入

- `consensus_fasta`：必填的 FASTA/FA/FNA/FAS 文件；
- `pathogen`：必须选择 `H1N1`、`H3N2` 或 `SARS_CoV_2`；
- `sample_id`、`log_tag`：可由 Agent 参数覆盖；
- 参考序列、snpEff 配置和数据库、segment 表及风险注释表由部署配置提供。

本包不接收 FASTQ，也不会执行 reads 比对或 consensus 生成。原始测序 reads 应先使用相应的 read-level variant risk workflow。

## 工作步骤和输出

工作流解压 snpEff 数据，调用 `run_consensus_risk.sh`，生成病原体特异的变异风险报告，并将完整输出打包。输出为最终风险报告 TSV 和完整输出 tar 包。

## Cromwell 部署要求

任务镜像默认为 `cncb/risk-wdl:v1.0`。`runner.yaml` 中的参考和注释资源路径必须是 Cromwell 任务主机及容器可读取的 Linux 路径，不是本机 Windows 路径。

启动 Agent 前需要配置 `CROMWELL_URL`，以及项目部署要求的输入/输出对象存储设置。

## 文件说明

- `workflow.wdl`：从 `wdl2agent/consensus-risk/consensus_risk.wdl` 复制的工作流；
- `runner.yaml`：Agent 的输入、参数、三病原体 presets 入口和输出合同；
- `inputs.json`：公共默认参数，不固定某一个病原体的资源库；
- `options.json`：Cromwell 输出选项。

结果依赖参考序列、风险注释库和阈值设置，属于分析证据，不等同于临床诊断。


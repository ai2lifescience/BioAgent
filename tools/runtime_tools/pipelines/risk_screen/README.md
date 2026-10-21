# ScreenMec biosafety sequence screening

这是 `ScreenMec` WDL 的 Agent 包装目录，适用于已经组装好或已经生成共识的核酸 FASTA。

## 输入

- `query_fasta`：必填的组装或共识 FASTA 文件；
- `sample_id`：样本名称，默认是 `SAMPLE`；
- ScreenMec 的 Bowtie2、BLAST、FunSoCs、TaxonKit 和注释资源：由部署参数提供。

工作流不接收 FASTQ，也不执行 reads 质控、组装或普通的物种分型。

## 工作步骤和输出

ScreenMec 按级联流程执行：先用 Bowtie2 筛查 biorisk 序列，再用 blastx 进行 UniRef100/FunSoCs 功能筛查，最后用 blastn、病原体谱系信息和低关注度规则完成筛查。输出为一个 `screenmec.tsv` 结果表。

## Cromwell 部署要求

任务镜像默认为 `cncb/screenmec:v1.0`。`runner.yaml` 中的数据库、索引、注释和 TaxonKit 路径是 Cromwell 任务主机及任务容器可读取的 Linux 路径，不是本机 Windows 路径；这些资源不会随本包复制或上传。启动 Agent 前需要在部署环境中挂载相应目录，并配置 `CROMWELL_URL` 及项目要求的输入/输出对象存储设置。

## 文件说明

- `workflow.wdl`：从 `wdl2agent/screenmec/screenmec.wdl` 原样复制的 WDL 工作流；
- `runner.yaml`：Agent 的 FASTA 输入、部署资源参数和输出合同；
- `inputs.json`：沿用原流程的数据库、注释和运行参数默认值；
- `options.json`：Cromwell 输出选项。

结果依赖数据库版本、注释版本、输入 FASTA 质量和运行参数，属于筛查结果，不等同于临床诊断。

# MetaX classification abundance analysis

这是 MetaX WDL 的 Agent 包装目录，用于对单个样本的 reads 或输入序列文件进行物种和分类学 profiling。

## 输入

- `reads`：必需的输入序列文件，可用于单端 reads、双端 read 1，或 MetaX 接受的 FASTA 文件；
- `reads2`：可选的双端测序 read 2。

提供 `reads2` 时，工作流会把两个文件拼接为 MetaX 的 paired-end 输入并启用 `-p`。工作流不会在 MetaX 之前执行质控或组装。

## 数据库和参数

- `db`：MetaX 数据库 JSON，默认使用原始示例中的挂载路径；
- `dmp_dir`：可选的 NCBI taxdump 目录，默认使用原始示例中的挂载路径；
- `sequencer`、`mode` 和各类过滤参数通过 `runner.yaml` 的 `param_overrides` 暴露；
- `keep_raw`、`compress_sam`、`by_aligned`、`resume` 等布尔参数对应 MetaX 命令行选项。

`db` 和 `dmp_dir` 指向 Cromwell 任务容器内的 Linux 路径，相关数据库和 `nodes.dmp`、`names.dmp`、`merged.dmp` 文件需要预先挂载，不会随 pipeline 包复制。

默认容器镜像是 `metax:0.9.23-beta`，线程数、内存和磁盘需求分别由 `threads`、`memory_gb` 和 `disk_gb` 控制。

## 输出

- `profile.txt`：MetaX 生成的单样本分类学 profile 表。

WDL 会根据输入文件名生成 MetaX 前缀，并从工作目录中选择第一个 `*.profile.txt` 作为 `metax.profile` 输出。

## Cromwell / Agent 使用

使用 `pipeline_name: metax_profiling`，上传 `reads`，双端数据另外上传 `reads2`，并确保 MetaX 数据库和 taxdump 路径在任务容器中可读。

`workflow.wdl` 从 `wdl2agent_complement/mscan-wdl/metax/metax.wdl` 原样复制；`runner.yaml` 定义 Agent 的输入、参数和输出合同；`inputs.json` 保留原 MetaX 的数据库和运行参数并移除了示例序列文件路径；`options.json` 配置 Cromwell 输出目录。

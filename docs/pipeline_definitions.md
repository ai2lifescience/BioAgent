# Pipeline manifest definitions

This document defines the contract for pipeline bundles under
tools/runtime_tools/pipelines. A pipeline bundle is a self-contained workflow
description, its engine files, and optional example data.

A runner.yaml file is **not** a model-facing SDK FunctionTool. The model calls the
native SDK ShellTool named pipeline_shell with the allowlisted agent-pipeline
protocol. The pipeline catalog reads runner.yaml, exposes its intent and
contracts to the agent, and the pipeline engine validates the selected plan.

## Recommended file layout

~~~text
tools/runtime_tools/pipelines/<pipeline-name>/
├── runner.yaml          # catalog, input/output, and execution contract
├── README.md            # human documentation and limitations
├── config.yaml          # optional engine configuration
├── run.sh               # shell entrypoint when engine: shell
├── Snakefile            # Snakemake entrypoint when engine: snakemake
├── main.nf              # Nextflow entrypoint when engine: nextflow
├── workflow.wdl         # WDL entrypoint when engine: wdl
├── inputs.json          # optional WDL input defaults
├── options.json         # optional WDL options
└── data/                # optional bundled demonstration data
~~~

Keep workflow code, engine configuration, and dependency assumptions inside the
bundle. The catalog discovers only directories containing runner.yaml.

## Metadata belongs at the top

Put the identity and selection metadata immediately after name. Put execution
configuration and detailed input/output contracts after it.

~~~yaml
name: bacterial_genome_annotation
display_name: Bacterial genome annotation
description: Annotate assembled bacterial contigs and produce normalized
  sequence, feature, report, and metrics artifacts.
visibility: public
use_when:
- the user has assembled bacterial contigs and wants gene annotation
avoid_when:
- the input is raw reads
- the user needs comparative variant analysis
input_summary: One assembled bacterial FASTA file.
output_summary: GFF, GenBank, protein, feature-table, report, and metrics files.
limitations: Results depend on the selected annotator and database versions.
examples:
- Annotate the genes in my assembled bacterial genome.

engine: shell
config: config.yaml
entrypoint: run.sh
timeout: 3600
inputs:
  genome:
    label: Assembled bacterial genome
    config_key: genome_path
    required: true
    accepts:
    - .fasta
    - .fa
    - .fna
    description: Assembled bacterial contigs in FASTA format.
outputs:
  report:
    label: Annotation report
    config_key: report_path
    default: output/report.md
    kind: report
    required: true
    description: Annotation report produced by this workflow.
execution:
  boundary: container
  dependency_scope: pipeline
  engine: shell
~~~

The parser uses YAML key names, not their order, so ordering is for readability,
catalog review, and maintenance. Keep this order consistent across bundles.

## Identity and selection fields

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| name | string | yes | Stable directory and catalog identifier. It should match the bundle directory. |
| display_name | string | yes | Human-readable name shown in the catalog and agent results. |
| description | string | yes | Short statement of the scientific or data-processing outcome. Describe the result, not the implementation. |
| visibility | public or internal | yes | public pipelines are normal user candidates; internal pipelines are demonstrations or runtime fixtures and should be selected only when requested. |
| use_when | list of strings | yes | User goals and data conditions that make this pipeline appropriate. |
| avoid_when | list of strings | yes | Similar or unsafe cases where another tool or pipeline should be used. |
| input_summary | string | yes | Concise description of the required input data and external resources. |
| output_summary | string | yes | Main artifacts and measurements produced by a successful run. |
| limitations | string | yes | Scientific, data, resource, engine, or deployment limitations. |
| examples | list of strings | recommended | Natural-language requests that should select this pipeline. |

These fields form the pipeline-selection contract. The model compares the full
catalog entry with the user's goal, available files, requested outputs, and
constraints. description is only one part of that decision.

Write selection metadata for intent:

Good:

~~~yaml
description: Compare assembled viral genomes to a reference, call nucleotide
  variants, and optionally infer a phylogeny.
use_when:
- the user wants mutation comparison across assembled viral genomes
avoid_when:
- the user has raw reads
- the user asks for clinical interpretation of mutations
~~~

Weak:

~~~yaml
description: Run viral_genome_mutation_analysis/run.sh.
~~~

The weak version describes an implementation detail and gives the agent no
information about when the pipeline is suitable.

## Execution fields

Common execution fields are:

| Field | Meaning |
| --- | --- |
| engine | Local adapter: shell, snakemake, nextflow, or wdl. |
| config | Optional base YAML configuration for shell or other local adapters. |
| entrypoint | Script used by a shell pipeline, normally run.sh. |
| snakefile | Snakemake workflow file. |
| workflow | Nextflow or WDL workflow file. |
| nextflow_config | Optional Nextflow configuration file. |
| inputs_json | Optional WDL input defaults file. |
| options_json | Optional WDL options file. |
| timeout | Maximum run time in seconds, bounded by the engine service. |
| cores | Default core count for supported workflow engines. |
| execution | Deployment metadata such as boundary, dependency_scope, and engine. |

Use only the fields required by the selected engine. WDL bundles may also use
cromwell_api_version, cromwell_poll_interval, and
cromwell_visibility_timeout when they support a Cromwell backend.

The execution boundary describes the intended dependency boundary. Local shell,
Snakemake, Nextflow, and miniwdl execution still runs through the configured
local worker unless deployment infrastructure provides containers. Do not claim
that a manifest alone creates a security container.

Pipeline dependencies should be supplied by the pipeline deployment or its
declared container image. Do not tell the agent to install workflow
dependencies into the main agent environment.

## Input declarations

The top-level inputs mapping defines named input slots. Each slot is a contract
the agent can fill during planning.

~~~yaml
inputs:
  reads:
    label: FASTQ reads
    config_key: input_path
    required: true
    accepts:
    - .fastq
    - .fq
    - .fastq.gz
    - .fq.gz
    multiple: false
    description: Single-end or paired-end reads supplied to the workflow.
  reference:
    label: Reference genome
    config_key: reference_path
    required: false
    accepts:
    - .fasta
    - .fa
    description: Reference used for local comparison.
~~~

| Field | Type | Meaning |
| --- | --- | --- |
| slot name | string | User-facing input slot used with --input SLOT=PATH. |
| label | string | Human-readable label for the slot. |
| config_key | string | Key written to the runtime configuration for shell-style pipelines. |
| wdl_key | string | Fully qualified WDL input name for WDL pipelines. |
| required | boolean | Whether planning must receive a value. |
| accepts | list | Allowed file suffixes. |
| multiple | boolean | Whether the slot accepts a list of files. |
| description | string | What the input contains and how it is used. |

Use config_key or wdl_key, not both, unless the adapter explicitly needs both.
Input paths supplied by the agent must be workspace-relative. The planner
confines them to the session workspace, checks that files exist, validates their
suffixes, and records their size and SHA-256 digest.

If required inputs are missing, planning returns needs_input with the declared
slots. The agent should ask the user for those inputs rather than guessing.

## Parameter declarations

Use param_overrides when a user-facing parameter maps to a runtime configuration
key or WDL input:

~~~yaml
param_overrides:
  annotator:
    config_key: annotator
    required: true
    choices:
    - prokka
    - bakta
  threads:
    config_key: threads
    default: 8
~~~

Supported parameter metadata includes:

- config_key, wdl_key, or key: runtime destination;
- default: value used when the user does not override it;
- required: planning must receive a value;
- choices: valid named values.

A pipeline may define preset_param and presets when one selection expands into a
validated group of runtime values:

~~~yaml
preset_param: pathogen
presets:
  influenza:
    reference: references/influenza.fa
    database: references/influenza
  sars_cov_2:
    reference: references/sars_cov_2.fa
    database: references/sars_cov_2
~~~

Do not expose arbitrary command-line text as a parameter. Use typed, bounded
values and validate them in the pipeline engine.

## Output declarations

The top-level outputs mapping describes artifacts that a successful run must
produce.

~~~yaml
outputs:
  report:
    label: Markdown report
    config_key: report_path
    default: output/report.md
    kind: report
    required: true
    description: Report produced by this workflow.
  metrics:
    label: Metrics
    config_key: metrics_path
    default: output/metrics.json
    kind: metrics
    required: true
    description: Machine-readable metrics produced by this workflow.
~~~

| Field | Meaning |
| --- | --- |
| label | Human-readable artifact name. |
| config_key | Runtime configuration key for output path. |
| wdl_output | Fully qualified WDL output expression. |
| target | Destination filename for WDL output collection. |
| default | Default path declared by the workflow. |
| kind | Artifact type such as report, table, metrics, sequence, annotation, tree, or alignment. |
| required | Whether a successful run must provide this output. |
| description | What the artifact contains. |

The planner confines declared outputs to the job workspace. The worker verifies
the pipeline definition and input digests, checks output confinement, writes an
output manifest, and records output hashes. Results can include verified files,
metrics, bounded table previews, and a ZIP bundle.

Output descriptions should explain the artifact's meaning. Do not describe a
file as successful evidence if the workflow only produces a candidate or
prediction.

## Catalog and tool selection

The model-facing selection path is:

~~~text
user request
  -> pipeline_shell: agent-pipeline catalog
  -> compare description, use_when, avoid_when, inputs, outputs, limitations
  -> pipeline_shell: agent-pipeline files
  -> choose workspace-relative input slots
  -> pipeline_shell: agent-pipeline plan
  -> validate inputs, parameters, resources, and output paths
  -> approval for agent-pipeline run
  -> durable worker
  -> status, bounded wait, and verified results
~~~

The catalog returns compact fields specifically for selection:

- name and display_name;
- visibility;
- description;
- use_when and avoid_when;
- input_summary and output_summary;
- limitations;
- input slots and output names;
- parameters and timeout.

A model may select an unsuitable workflow when two entries overlap or the user
is ambiguous. Improve selection by making metadata specific and non-overlapping,
not by adding a second keyword router. For high-risk or ambiguous work, require
the agent to show the selected pipeline and plan before approval.

## Pipeline safety and lifecycle

A normal run should follow:

1. Discover the catalog.
2. Inspect the session files.
3. Ask for missing inputs or parameters.
4. Create a plan.
5. Show the plan and wait for approval.
6. Run the saved plan.
7. Inspect status or wait for a bounded period.
8. Collect results without rerunning.
9. Explain limitations and preserve output paths.

The pipeline shell accepts one allowlisted agent-pipeline command at a time. It
does not accept arbitrary Bash, pipes, redirects, command substitution, or a
workspace override.

Pipeline execution and cancellation require SDK approval. Catalog, files,
example staging, planning, status, bounded wait, and result inspection do not.
A queued or running job is not a successful result. Interrupted jobs are not
automatically replayed because engines and tools may have side effects.

## Author checklist

Before adding or changing a manifest:

- Put identity and selection metadata first.
- Describe user outcomes, not filenames or implementation commands.
- Add at least one useful use_when and avoid_when entry.
- Declare every required input and output.
- Use workspace-relative input and output paths.
- Bound timeout, cores, memory, parameters, and accepted suffixes.
- State reference, database, engine, and interpretation limitations.
- Mark demonstrations internal.
- Validate the bundle with the pipeline configuration smoke test.
- Add a representative prompt to docs/web_usage.md when the user-facing intent
  is new.
- Update tools/runtime_tools/pipelines/README.md when the catalog changes.

For the agent-facing protocol, see
[architecture.md](architecture.md#pipeline-runtime). For external website
embedding, see [web_integration.md](web_integration.md).

# Pipeline catalog

Each directory is a self-contained bundle. `runner.yaml` is the agent-facing contract for intent, inputs, outputs, and execution.

See [pipeline manifest definitions](../../../docs/pipeline_definitions.md) for
the field order, selection metadata, input/output schema, and validation rules.

Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

WDL pipelines use local miniwdl by default. For remote Cromwell, use the
[Cromwell and S3 setup](../../../docs/web_usage.md#wdl-execution-backend).
It contains the complete environment configuration for the Mscan server:
one Cromwell URL, S3 input/output prefixes, and one set of storage credentials.
Output downloads reuse the input-storage endpoint, region, and credentials.

BioAgent uploads inputs to S3, submits WDL through the Cromwell REST API, and
downloads the files declared in `runner.yaml` after success. Downloaded outputs
are validated and hashed in the local job directory. The input and output mount
prefixes describe existing paths on the Cromwell/task hosts; BioAgent needs no
shared filesystem mount. Reference databases remain mounted on the task hosts.

Supply credentials through the environment before starting BioAgent. The
adapter does not automatically read Mscan's configuration. Detached pipeline
workers receive the same Cromwell and S3 settings. Unset `CROMWELL_URL` and
restart BioAgent to return to local execution.

| Name | Visibility | Engine | Use when |
| --- | --- | --- | --- |
| `antimicrobial_resistance_detection` | `public` | `shell` | `the user wants resistance gene or AMR evidence from contigs or reads` |
| `bacterial_functional_annotation` | `public` | `shell` | `the user wants gene function or orthology annotations from bacterial sequence data` |
| `bacterial_genome_annotation` | `public` | `shell` | `the user has assembled bacterial contigs and wants gene or feature annotation` |
| `bacterial_genome_mutation_analysis` | `public` | `shell` | `the user wants mutation comparison or a phylogeny from assembled bacterial genomes` |
| `bacterial_read_variant_analysis` | `public` | `shell` | `the user wants variant comparison from bacterial FASTQ reads` |
| `bacterial_virulence_factor_detection` | `public` | `shell` | `the user wants virulence-factor sequence candidates from contigs or reads` |
| `metagenomic_de_novo_assembly` | `public` | `wdl` | `the user wants assembly and downstream identification from metagenomic reads` |
| `metagenomic_pathogen_identification` | `public` | `wdl` | `the user wants pathogen detection from cleaned metagenomic reads` |
| `metagenomic_read_quality_control` | `public` | `wdl` | `the user wants quality filtering and host removal from metagenomic reads` |
| `pathogen_variant_risk_assessment` | `public` | `wdl` | `the user wants configured pathogen variant calling and risk tables from clean reads` |
| `rna_secondary_structure_prediction` | `public` | `shell` | `the user wants secondary-structure predictions for RNA or DNA-letter nucleotide sequences` |
| `template_bio` | `internal` | `shell` | `the user requests a local demonstration of the pipeline runtime` |
| `template_nextflow` | `internal` | `nextflow` | `the user requests a Nextflow runtime demonstration` |
| `template_shell` | `internal` | `shell` | `the user wants sequence IDs matched to metadata categories` |
| `template_snakemake` | `internal` | `snakemake` | `the user requests a Snakemake runtime demonstration` |
| `template_wdl` | `internal` | `wdl` | `the user requests a WDL runtime demonstration` |
| `viral_genome_mutation_analysis` | `public` | `shell` | `the user wants mutation comparison across assembled viral genomes` |
| `viral_molecular_typing` | `public` | `wdl` | `the user wants configured influenza or SARS-CoV-2 read processing and typing` |

Template entries are internal examples for testing an engine or copying a bundle structure.

# Pipeline catalog

Each directory is a self-contained bundle. `runner.yaml` is the agent-facing contract for intent, inputs, outputs, and execution.

See [pipeline manifest definitions](../../../docs/pipeline_definitions.md) for
the field order, selection metadata, input/output schema, and validation rules.

Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

WDL pipelines use local miniwdl by default. Set `CROMWELL_URL` before starting
BioAgent to submit WDL jobs to that Cromwell service, or unset it to return to
local execution. See the [startup commands](../../../README.md#4-start-the-web-ui).

When the Cromwell host cannot see BioAgent's local workspace, inputs can be
staged to an S3-compatible bucket before submission. Install the project
requirements, configure credentials using the normal boto3 environment or
instance profile, and set:

```bash
export CROMWELL_URL=http://192.168.164.39:39000
export CROMWELL_INPUT_STORAGE_ENDPOINT=http://192.168.164.39:7070
export CROMWELL_INPUT_STORAGE_URI=s3://cncb-web-server-mic/files
export CROMWELL_INPUT_STORAGE_REGION=us-east-1
export CROMWELL_INPUT_STORAGE_MOUNT_PREFIX=/data/versitygw/data/s3
```

Set `CROMWELL_INPUT_STORAGE_ACCESS_KEY` and
`CROMWELL_INPUT_STORAGE_SECRET_KEY` if the S3 service is not available through
the normal boto3/AWS credential chain. `CROMWELL_INPUT_STORAGE_ENDPOINT` is the
S3-compatible service address, while `CROMWELL_INPUT_STORAGE_URI` selects the
bucket and key prefix. `CROMWELL_INPUT_STORAGE_MOUNT_PREFIX` is the filesystem
root visible to Cromwell. With the example above, an uploaded object is passed
to Cromwell as `/data/versitygw/data/s3/cncb-web-server-mic/files/...` while
the upload is also recorded as an S3 URI. Paths that are not local files, such
as remote mounted reference databases, are left unchanged.

The endpoint, existing bucket, region, and mount above match the administrator's
`resource/mscan-app/mscan-admin/src/main/resources/application-prod.yml`.
Supply its S3 credentials through the environment before starting BioAgent;
the adapter does not automatically read that backend configuration. A live
probe on 2026-09-25 verified upload and a Cromwell read of the mounted file.

This stages inputs only. The adapter currently collects declared outputs from
local paths returned by Cromwell, so those paths must be visible to BioAgent.
Automatic retrieval of remote S3 outputs is not implemented.

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

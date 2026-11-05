# Pipeline catalog

Each directory is a self-contained bundle. `runner.yaml` is the agent-facing contract for intent, inputs, outputs, and execution.

See [pipeline manifest definitions](../../../docs/pipeline_definitions.md) for
the field order, selection metadata, input/output schema, and validation rules.

Pipeline dependencies and databases belong to the pipeline container. The BioAgent environment does not install workflow tools.

In local/trusted mode, WDL pipelines use miniwdl by default; isolated mode uses
Cromwell/S3. For remote Cromwell, use the
[Cromwell and S3 setup](../../../docs/web_usage.md#wdl-execution-backend).
It contains the complete environment configuration for the Mscan server:
one Cromwell URL, S3 input/output prefixes, and one set of storage credentials.
Output downloads reuse the input-storage endpoint, region, and credentials.

BioAgent uploads declared file inputs to S3 and submits WDL through the Cromwell
REST API. The ordinary executor downloads declared outputs after success. The
isolated broker registers owned remote artifact references and streams downloads
on demand; Workspace Import creates a local copy for analysis. The input and output mount
prefixes describe existing paths on the Cromwell/task hosts; BioAgent needs no
shared filesystem mount. Reference databases remain mounted on the task hosts.

Supply credentials through the environment before starting BioAgent. The
adapter does not automatically read Mscan's configuration. Detached pipeline
workers receive the same Cromwell and S3 settings. Unset `CROMWELL_URL` and
restart a local/trusted BioAgent instance to return to miniwdl. Isolated WDL
execution still requires Cromwell/S3.

| Name | Visibility | Engine | Use when |
| --- | --- | --- | --- |
| `antimicrobial_resistance_detection` | `public` | `shell` | `the user wants resistance gene or AMR evidence from contigs or reads` |
| `bacterial_biosynthetic_gene_clusters` | `public` | `wdl` | `the user wants bacterial secondary-metabolite or biosynthetic gene cluster detection` |
| `bacterial_defense_system_annotation` | `public` | `wdl` | `the user wants bacterial defense-system annotation or DefenseFinder results` |
| `bacterial_functional_annotation` | `public` | `shell` | `the user wants gene function or orthology annotations from bacterial sequence data` |
| `bacterial_genome_annotation` | `public` | `shell` | `the user has assembled bacterial contigs and wants gene or feature annotation` |
| `bacterial_genome_mutation_analysis` | `public` | `shell` | `the user wants mutation comparison or a phylogeny from assembled bacterial genomes` |
| `bacterial_read_variant_analysis` | `public` | `shell` | `the user wants variant comparison from bacterial FASTQ reads` |
| `bacterial_secretion_system_annotation` | `public` | `wdl` | `the user wants bacterial secretion-system annotation or TXSScan results` |
| `bacterial_viral_variant_analysis` | `public` | `wdl` | `the user wants bacterial or viral SNP and variant results from one sample` |
| `bacterial_virulence_factor_detection` | `public` | `shell` | `the user wants virulence-factor sequence candidates from contigs or reads` |
| `genomic_pathogen_identification` | `public` | `wdl` | `the user has an assembled or consensus FASTA and wants Mash-based pathogen identification` |
| `metagenomic_de_novo_assembly` | `public` | `wdl` | `the user wants assembly and downstream identification from metagenomic reads` |
| `metagenomic_growth_rate_Calculation` | `public` | `wdl` | `the user has single-end or paired-end metagenomic FASTQ reads and wants CoPTR replication-rate estimates` |
| `metagenomic_pathogen_identification` | `public` | `wdl` | `the user wants pathogen detection from cleaned metagenomic reads` |
| `metagenomic_pathogen_identification_kmer` | `public` | `wdl` | `the user has cleaned FASTQ reads and wants k-mer or strobemer based taxonomic detection` |
| `metagenomic_pathogen_identification_marker` | `public` | `wdl` | `the user has single-end or paired-end metagenomic FASTQ reads and wants MetaPhlAn-based community or strain profiling` |
| `metagenomic_qc_UniVec_Host` | `public` | `wdl` | `the user wants adapter trimming, host removal, or UniVec filtering for metagenomic FASTQ reads` |
| `metagenomic_read_quality_control` | `public` | `wdl` | `the user wants quality filtering and host removal from metagenomic reads` |
| `metax_classification_abundance_analysis` | `public` | `wdl` | `the user wants MetaX taxonomic profiling for a single sample` |
| `pathogen_variant_risk_assessment` | `public` | `wdl` | `the user wants configured pathogen variant calling and risk tables from clean reads` |
| `pathogen_variant_risk_assessment_consensus` | `public` | `wdl` | `the user already has a consensus FASTA and wants configured H1N1, H3N2, or SARS-CoV-2 variant risk analysis` |
| `phi_annotator_genome` | `public` | `wdl` | `the user has an assembled genome FASTA or a predicted protein FASTA and wants PHI-base annotation` |
| `phi_annotator_metagenome` | `public` | `wdl` | `the user has single-end or paired-end metagenomic FASTQ reads and wants PHI-base read-level annotation` |
| `risk_screen` | `public` | `wdl` | `the user has an assembled or consensus FASTA and wants biosafety or pathogen sequence screening` |
| `rna_secondary_structure_prediction` | `public` | `shell` | `the user wants secondary-structure predictions for RNA or DNA-letter nucleotide sequences` |
| `tcdb_annotator_genome` | `public` | `wdl` | `the user has an assembled genome FASTA or a predicted protein FASTA and wants TCDB annotation` |
| `tcdb_annotator_metagenome` | `public` | `wdl` | `the user has single-end or paired-end metagenomic FASTQ reads and wants read-level TCDB annotation` |
| `template_bio` | `internal` | `shell` | `the user requests a local demonstration of the pipeline runtime` |
| `template_nextflow` | `internal` | `nextflow` | `the user requests a Nextflow runtime demonstration` |
| `template_shell` | `internal` | `shell` | `the user wants sequence IDs matched to metadata categories` |
| `template_snakemake` | `internal` | `snakemake` | `the user requests a Snakemake runtime demonstration` |
| `template_wdl` | `internal` | `wdl` | `the user requests a WDL runtime demonstration` |
| `traceback_covid19` | `public` | `wdl` | `the user has a query FASTA and wants reference-based genotype distance, SNP sequence, and phylogenetic tree results` |
| `viral_genome_molecular_typing` | `public` | `wdl` | `the user already has a viral genome or consensus FASTA and wants influenza or SARS-CoV-2 molecular typing` |
| `viral_genome_mutation_analysis` | `public` | `shell` | `the user wants mutation comparison across assembled viral genomes` |
| `viral_molecular_typing` | `public` | `wdl` | `the user wants configured influenza or SARS-CoV-2 read processing and typing` |
| `viral_read_molecular_typing` | `public` | `wdl` | `the user has raw viral FASTQ or FASTQ.GZ reads and wants influenza or SARS-CoV-2 molecular typing` |

Template entries are internal examples for testing an engine or copying a bundle structure.

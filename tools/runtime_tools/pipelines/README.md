# Pipeline catalog

Each folder is a self-contained pipeline bundle. The `runner.yaml` manifest is the agent-facing contract: it explains when to use the workflow, the inputs it needs, the artifacts it produces, and its limitations.

Pipeline dependencies belong to the bundle container. The Pipeline2Agent Python environment does not install workflow tools or databases.

| Name | Visibility | Engine | Use when |
| --- | --- | --- | --- |
| `antimicrobial_resistance_detection` | public | shell | the user wants resistance gene or AMR evidence from contigs or reads |
| `bacterial_functional_annotation` | public | shell | the user wants gene function or orthology annotations from bacterial sequence data |
| `bacterial_genome_annotation` | public | shell | the user has assembled bacterial contigs and wants gene or feature annotation |
| `bacterial_genome_mutation_analysis` | public | shell | the user wants mutation comparison or a phylogeny from assembled bacterial genomes |
| `bacterial_read_variant_analysis` | public | shell | the user wants variant comparison from bacterial FASTQ reads |
| `bacterial_virulence_factor_detection` | public | shell | the user wants virulence-factor sequence candidates from contigs or reads |
| `dna_analysis_demo` | internal | shell | the user requests a local demonstration of the pipeline runtime |
| `metagenomic_de_novo_assembly` | public | wdl | the user wants assembly and downstream identification from metagenomic reads |
| `metagenomic_pathogen_identification` | public | wdl | the user wants pathogen detection from cleaned metagenomic reads |
| `metagenomic_read_quality_control` | public | wdl | the user wants quality filtering and host removal from metagenomic reads |
| `pathogen_variant_risk_assessment` | public | wdl | the user wants configured pathogen variant calling and risk tables from clean reads |
| `rna_secondary_structure_prediction` | public | shell | the user wants secondary-structure predictions for RNA or DNA-letter nucleotide sequences |
| `sequence_metadata_assignment` | internal | shell | the user wants sequence IDs matched to metadata categories |
| `sequence_normalization_nextflow_demo` | internal | nextflow | the user requests a Nextflow runtime demonstration |
| `sequence_normalization_snakemake_demo` | internal | snakemake | the user requests a Snakemake runtime demonstration |
| `sequence_normalization_wdl_demo` | internal | wdl | the user requests a WDL runtime demonstration |
| `sequence_qc_demo` | internal | shell | the user explicitly requests a runtime demonstration or smoke test |
| `viral_genome_mutation_analysis` | public | shell | the user wants mutation comparison across assembled viral genomes |
| `viral_molecular_typing` | public | wdl | the user wants configured influenza or SARS-CoV-2 read processing and typing |

Internal entries are runtime demonstrations and should be selected only when the user asks for a demo or smoke test.

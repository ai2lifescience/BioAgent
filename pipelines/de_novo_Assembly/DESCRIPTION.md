# De novo Assembly Pipeline Description

## Function

This WDL 1.0 workflow assembles metagenomic reads and identifies assembled
contigs against bacterial, fungal, parasite, and viral reference databases.

```text
single-end or paired-end FASTQ
  -> MEGAHIT de novo assembly
  -> read-to-contig alignment and support/soft-clipping statistics
  -> minimap2 identification against four reference databases
  -> optional MetaQUAST evaluation
  -> assembled contigs plus contig- and species-level reports
```

## Inputs

- `AssemblyId.fastq_r1`: required read 1 FASTQ.
- `AssemblyId.fastq_r2`: optional read 2 FASTQ; omitting it runs single-end.
- `AssemblyId.sample_id`: sample identifier used in task paths and reports.
- `AssemblyId.db_bacteria`, `db_fungi`, `db_parasite`, and `db_virus`:
  minimap2 index paths.
- `AssemblyId.annot_pathogen` and `annot_virus`: identification annotation
  tables.
- `AssemblyId.fasta_bacteria`, `fasta_fungi`, `fasta_parasite`, and
  `fasta_virus`: reference FASTA paths used during optional evaluation.
- `AssemblyId.do_evaluate`: enables MetaQUAST; defaults to `true`.

Assembly, minimap2, soft-clipping, MetaQUAST, resource, and Docker settings are
defined in `inputs.json`. Common runtime settings can be changed through the
parameter overrides declared in `runner.yaml`.

The database indexes, annotation tables, and supplied reference FASTA files
are WDL `File` inputs. The WDL engine localizes them into each task container,
so task scripts receive container-visible paths. FASTA inputs are optional,
but are needed for fallback alignment and for MetaQUAST evaluation.

## Outputs

- `final.contigs.renamed.fa`: renamed assembled contigs.
- `contig_report.tsv`: contig-level identification and support report.
- `species_report.tsv`: aggregated species-level report.
- `AssemblyId.paf_files`: raw minimap2 PAF files retained by the WDL engine.

BioAgent collects the three primary outputs under `data/output/`, as declared
in `runner.yaml`. Raw PAF files remain available in Cromwell's execution or
final-output directory because BioAgent's current output contract collects
scalar files.

BioAgent submits this workflow through the Cromwell Server REST API, polls its
status, records the workflow ID and metadata in the run directory, and copies
the declared outputs after Cromwell reports `Succeeded`.

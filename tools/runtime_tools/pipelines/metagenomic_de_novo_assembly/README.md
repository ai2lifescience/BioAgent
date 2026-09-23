# Metagenomic de novo assembly

This WDL 1.0 workflow assembles metagenomic reads with MEGAHIT, maps reads back
to contigs, identifies contigs against bacterial/fungal/parasite/viral
minimap2 indexes, and optionally evaluates the assembly with MetaQUAST.

## Requirements

Standalone execution requires:

- miniwdl for local execution, or Java for the standalone Cromwell command;
- a reachable Cromwell Server when using REST submission, with shared paths
  visible to BioAgent, Cromwell, and its task backend;
- Docker or the configured task backend with `cncb/assembly-id:v1.0` (or a
  compatible image) available;
- the assembly database indexes, annotation tables, and optional reference
  FASTAs declared in `inputs.json`;
- enough resources for the defaults: up to 32 CPUs, 64 GB RAM, and 500 GB
  working disk.

The task image must provide `/app/scripts/run_assembly.sh`,
`run_read_support.sh`, `run_identify.sh`, and `run_evaluate.sh`. The database
files are not included in this bundle. Replace the example paths in
`inputs.json` with paths readable by Cromwell and the task containers.

BioAgent uses local miniwdl by default when `CROMWELL_URL` is unset. To submit
to Cromwell, set its endpoint before starting the BioAgent server:

```bash
export CROMWELL_URL=http://192.168.164.39:39000
curl "$CROMWELL_URL/engine/v1/status"
```

To switch back to local miniwdl and Docker before restarting BioAgent:

```bash
unset CROMWELL_URL
```

The choice is captured in each pipeline plan, so the detached worker uses the
same backend selected at planning time.

## Inputs and workflow

- `AssemblyId.fastq_r1`: required FASTQ/FASTQ.GZ read 1;
- `AssemblyId.fastq_r2`: optional paired read 2;
- `AssemblyId.sample_id`: sample identifier;
- `AssemblyId.db_bacteria`, `db_fungi`, `db_parasite`, and `db_virus`:
  minimap2 indexes;
- `AssemblyId.annot_pathogen` and `annot_virus`: annotation tables;
- `AssemblyId.fasta_*`: optional reference FASTAs for evaluation;
- `AssemblyId.do_evaluate`: enables MetaQUAST.

`megahit_*`, minimap2, CPU, memory, disk, and Docker settings are also in
`inputs.json`. WDL `File` inputs must resolve to paths visible in the task
container, not only on the submitter's host.

## Run standalone

From this directory, edit a copy of the input JSON, then submit the workflow:

```bash
cp inputs.json inputs.local.json
# Replace the FASTQ and every database/annotation path in inputs.local.json.
java -jar cromwell.jar run assembly_id.wdl \
  -i inputs.local.json -o options.json
```

Cromwell writes the task output directory according to `options.json`. A local
Cromwell server can be used instead of the CLI; the BioAgent runtime submits
through its REST API, polls status, and collects the declared files.

## Outputs

The stable outputs are:

- `final.contigs.renamed.fa`;
- `contig_report.tsv`;
- `species_report.tsv`.

Raw minimap2 PAF files, logs, and MetaQUAST output remain in Cromwell's
execution/output directory. BioAgent copies the three declared files to the
pipeline run's `data/output/` directory.

## BioAgent use and limits

Use `pipeline_name: metagenomic_de_novo_assembly` with `read1` and optional
`read2`. The bundled FASTQ is a fixture; it cannot run until the database paths
and task image in `inputs.json` are replaced. Assembly and identification
quality depends on read depth, databases, image versions, and Cromwell resource
configuration.

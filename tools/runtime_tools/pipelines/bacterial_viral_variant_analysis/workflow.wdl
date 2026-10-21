version 1.0

# One maintainable workflow covering four existing implementations:
#   metagenome + bacteria -> bactmut_fastq
#   metagenome + virus    -> virmut fastq
#   genome     + bacteria -> bactmut_fasta
#   genome     + virus    -> virmut fasta
#
# One sample per run. Inputs are always files (never a directory):
#   metagenome: file1Path [= SE FASTQ], optional file2Path [= PE R2]
#   genome:     file1Path [= one assembly FASTA]; file2Path not allowed
workflow MutationAnalysis {
  input {
    String input_type             # metagenome | genome
    String organism               # bacteria | virus

    File file1Path                # SE FASTQ / R1, or single assembly FASTA
    File? file2Path               # PE R2 (metagenome only)

    File? reference               # local FASTA; bacteria/virus (Cromwell-localized)
    String? species               # bacteria only; requires reference_accession
    String? taxonid               # bacteria only; requires reference_accession
    String? reference_accession   # virus: DB accession; bacteria: alone or with species/taxonid

    String gtdb_db_path       = ""
    String gtdb_metadata_path = ""
    String virus_db_path      = ""
    String virus_metadata_path = ""

    Int threads          = 8
    Float min_coverage   = 0.9
    Int window_size      = 50
    Int step_size        = 10
    Float sd_threshold   = 3.0
    String aligner       = "auto"

    String docker_image = "cncb/snp-mutation:v1.0"
    Int cpu              = 8
    Int memory_gb        = 32
    Int disk_gb          = 200
  }

  call RunMutationAnalysis {
    input:
      input_type          = input_type,
      organism            = organism,
      file1Path           = file1Path,
      file2Path           = file2Path,
      reference           = reference,
      species             = species,
      reference_accession = reference_accession,
      taxonid             = taxonid,
      gtdb_db_path        = gtdb_db_path,
      gtdb_metadata_path  = gtdb_metadata_path,
      virus_db_path       = virus_db_path,
      virus_metadata_path = virus_metadata_path,
      threads             = threads,
      min_coverage        = min_coverage,
      window_size         = window_size,
      step_size           = step_size,
      sd_threshold        = sd_threshold,
      aligner             = aligner,
      docker_image        = docker_image,
      cpu                 = cpu,
      memory_gb           = memory_gb,
      disk_gb             = disk_gb
  }

  output {
    File snp_matrix       = RunMutationAnalysis.snp_matrix
    File variants_tsv     = RunMutationAnalysis.variants_tsv
    File variants_summary = RunMutationAnalysis.variants_summary
  }
}

task RunMutationAnalysis {
  input {
    String input_type
    String organism
    File file1Path
    File? file2Path
    File? reference
    String? species
    String? reference_accession
    String? taxonid
    String gtdb_db_path
    String gtdb_metadata_path
    String virus_db_path
    String virus_metadata_path
    Int threads
    Float min_coverage
    Int window_size
    Int step_size
    Float sd_threshold
    String aligner
    String docker_image
    Int cpu
    Int memory_gb
    Int disk_gb
  }

  command <<<
    set -euo pipefail

    REFERENCE="~{if defined(reference) then select_first([reference]) else ''}"
    SPECIES="~{if defined(species) then select_first([species]) else ''}"
    REFERENCE_ACCESSION="~{if defined(reference_accession) then select_first([reference_accession]) else ''}"
    TAXONID="~{if defined(taxonid) then select_first([taxonid]) else ''}"
    FILE1="~{file1Path}"
    FILE2="~{if defined(file2Path) then select_first([file2Path]) else ''}"

    if [ ! -f "$FILE1" ]; then
      echo "file1Path must be a readable file: $FILE1" >&2
      exit 1
    fi

    if [ "~{input_type}" = "genome" ] && [ -n "$FILE2" ]; then
      echo "genome runs one assembly FASTA per sample; omit file2Path" >&2
      exit 1
    fi

    # Stage one sample into a directory for the existing tools.
    mkdir -p staged_input
    suffix_of() {
      case "$1" in
        *.fastq.gz|*.FASTQ.GZ) echo ".fastq.gz" ;;
        *.fq.gz|*.FQ.GZ)       echo ".fq.gz" ;;
        *.fastq|*.FASTQ)       echo ".fastq" ;;
        *.fq|*.FQ)             echo ".fq" ;;
        *.fasta.gz|*.FASTA.GZ|*.fa.gz|*.FA.GZ|*.fna.gz|*.FNA.GZ) echo ".fasta.gz" ;;
        *.fasta|*.FASTA)       echo ".fasta" ;;
        *.fna|*.FNA)           echo ".fna" ;;
        *.fa|*.FA)             echo ".fa" ;;
        *.fas|*.FAS)           echo ".fas" ;;
        *)
          if [ "~{input_type}" = "genome" ]; then
            echo ".fasta"
          else
            echo ".fastq.gz"
          fi
          ;;
      esac
    }

    EXT1=$(suffix_of "$FILE1")
    if [ -n "$FILE2" ]; then
      if [ ! -f "$FILE2" ]; then
        echo "file2Path is set but not a readable file: $FILE2" >&2
        exit 1
      fi
      EXT2=$(suffix_of "$FILE2")
      ln -sf "$FILE1" "staged_input/sample_R1${EXT1}"
      ln -sf "$FILE2" "staged_input/sample_R2${EXT2}"
    else
      ln -sf "$FILE1" "staged_input/sample${EXT1}"
    fi
    INPUT_ARG="staged_input"

    ARGS=(
      --input-type "~{input_type}"
      --organism "~{organism}"
      --input "$INPUT_ARG"
      --output results
      --threads ~{threads}
      --min-coverage ~{min_coverage}
      --window-size ~{window_size}
      --step-size ~{step_size}
      --sd-threshold ~{sd_threshold}
      --aligner "~{aligner}"
      --skip-tree
    )

    if [ -n "$REFERENCE" ]; then ARGS+=(--reference "$REFERENCE"); fi
    if [ -n "$SPECIES" ]; then ARGS+=(--species "$SPECIES"); fi
    if [ -n "$REFERENCE_ACCESSION" ]; then ARGS+=(--reference-accession "$REFERENCE_ACCESSION"); fi
    if [ -n "$TAXONID" ]; then ARGS+=(--taxonid "$TAXONID"); fi
    if [ -n "~{gtdb_db_path}" ]; then ARGS+=(--gtdb-db-path "~{gtdb_db_path}"); fi
    if [ -n "~{gtdb_metadata_path}" ]; then ARGS+=(--gtdb-metadata-path "~{gtdb_metadata_path}"); fi
    if [ -n "~{virus_db_path}" ]; then ARGS+=(--virus-db-path "~{virus_db_path}"); fi
    if [ -n "~{virus_metadata_path}" ]; then ARGS+=(--virus-metadata-path "~{virus_metadata_path}"); fi

    python3 /app/unified_runner.py "${ARGS[@]}" 2>&1 | tee pipeline.log

    mkdir -p deliverables
    if [ -f results/matrix.tsv ]; then
      cp -f results/matrix.tsv deliverables/snp_matrix
    elif [ -f results/filtered_snp_matrix.fasta ]; then
      cp -f results/filtered_snp_matrix.fasta deliverables/snp_matrix
    else
      echo "SNP matrix was not produced" >&2
      exit 1
    fi
    [ -f results/variants.tsv ] && cp -f results/variants.tsv deliverables/variants.tsv || touch deliverables/variants.tsv
    [ -f results/variants_summary.txt ] && cp -f results/variants_summary.txt deliverables/variants_summary.txt || touch deliverables/variants_summary.txt
  >>>

  output {
    File snp_matrix       = "deliverables/snp_matrix"
    File variants_tsv     = "deliverables/variants.tsv"
    File variants_summary = "deliverables/variants_summary.txt"
  }

  runtime {
    docker: docker_image
    cpu: cpu
    memory: "~{memory_gb} GB"
    disks: "local-disk ~{disk_gb} SSD"
  }
}
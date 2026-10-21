version 1.0

# BacSec: bacterial secretion-system annotation. The workflow accepts one
# unified main file and uses input_type to select genome or read mode.
workflow BacSec {
  input {
    String sample_id
    String input_type
    File file1Path
    File? file2Path
    String txsscan_models_dir
    String docker_image = "cncb/bacsec:v2"
    Int threads = 8
    Int min_contig_length = 1000
    String genome_context = "auto"
    Int memory_gb = 32
    Int disk_gb = 100
  }

  if (input_type == "genome") {
    call NormalizeFasta as NormalizeGenome { input: fasta = file1Path, sample_id = sample_id, min_contig_length = min_contig_length, docker_image = docker_image }
  }
  if (input_type == "metagenome") {
    call AssembleReads { input: read1 = file1Path, read2 = file2Path, threads = threads, min_contig_length = min_contig_length, docker_image = docker_image, memory_gb = memory_gb, disk_gb = disk_gb }
    call NormalizeFasta as NormalizeAssembly { input: fasta = AssembleReads.contigs, sample_id = sample_id, min_contig_length = min_contig_length, docker_image = docker_image }
  }
  File normalized_fasta = select_first([NormalizeGenome.normalized_fasta, NormalizeAssembly.normalized_fasta])
  File contig_mapping = select_first([NormalizeGenome.contig_mapping, NormalizeAssembly.contig_mapping])
  String selected_context = if (genome_context == "auto") then (if (input_type == "genome") then "complete" else "metagenome") else genome_context

  call CallSecretionSystems {
    input: normalized_fasta = normalized_fasta, contig_mapping = contig_mapping,
      txsscan_models_dir = txsscan_models_dir, threads = threads,
      sample_id = sample_id,
      prodigal_mode = if (selected_context == "complete") then "single" else "meta",
      docker_image = docker_image, memory_gb = memory_gb, disk_gb = disk_gb
  }

  output {
    File secretion_systems = CallSecretionSystems.systems
    File secretion_genes = CallSecretionSystems.genes
  }
}
task AssembleReads {
  input {
    File read1
    File? read2
    Int threads
    Int min_contig_length
    String docker_image
    Int memory_gb
    Int disk_gb
  }
  command <<<
    set -euo pipefail
    if [[ -n "~{if defined(read2) then select_first([read2]) else ""}" ]]; then
      fastp -i ~{read1} -I ~{select_first([read2])} -o trimmed_R1.fastq.gz -O trimmed_R2.fastq.gz --thread ~{if (threads < 16) then threads else 16} --json fastp.json --html fastp.html
      megahit -1 trimmed_R1.fastq.gz -2 trimmed_R2.fastq.gz -o megahit -t ~{threads} --min-contig-len ~{min_contig_length}
    else
      fastp -i ~{read1} -o trimmed.fastq.gz --thread ~{if (threads < 16) then threads else 16} --json fastp.json --html fastp.html
      megahit -r trimmed.fastq.gz -o megahit -t ~{threads} --min-contig-len ~{min_contig_length}
    fi
    cp megahit/final.contigs.fa contigs.fasta
  >>>
  output {
    File contigs = "contigs.fasta"
    File fastp_json = "fastp.json"
    File fastp_html = "fastp.html"
  }
  runtime { docker: docker_image cpu: threads memory: memory_gb + " GB" disks: "local-disk " + disk_gb + " SSD" }
}

task NormalizeFasta {
  input {
    File fasta
    String sample_id
    Int min_contig_length
    String docker_image
  }
  command <<<
    set -euo pipefail
    INPUT=~{fasta}
    if [[ "$INPUT" == *.gz ]]; then READER=(gzip -cd -- "$INPUT"); else READER=(cat -- "$INPUT"); fi
    "${READER[@]}" | awk -v sample="~{sample_id}" -v minlen=~{min_contig_length} '
      BEGIN { print "replicon_id\tcontig_id\tlength_bp" > "contig_mapping.tsv" }
      function emit() { if (name != "" && length(seq) >= minlen) { n++; id=sample "C" sprintf("%06d",n); print ">" id > "normalized_contigs.fna"; for (i=1;i<=length(seq);i+=80) print substr(seq,i,80) > "normalized_contigs.fna"; print id "\t" name "\t" length(seq) > "contig_mapping.tsv" } }
      /^>/ { emit(); name=substr($0,2); sub(/[ \t].*/,"",name); seq=""; next } { gsub(/[ \t\r]/,"",$0); seq=seq toupper($0) } END { emit(); if (n==0) exit 2 }'
  >>>
  output {
    File normalized_fasta = "normalized_contigs.fna"
    File contig_mapping = "contig_mapping.tsv"
  }
  runtime { docker: docker_image }
}

task CallSecretionSystems {
  input {
    File normalized_fasta
    File contig_mapping
    String sample_id
    String txsscan_models_dir
    Int threads
    String prodigal_mode
    String docker_image
    Int memory_gb
    Int disk_gb
  }
  command <<<
    set -euo pipefail
    prodigal -i ~{normalized_fasta} -a proteins.faa -d genes.fna -f gff -o genes.gff -p ~{prodigal_mode} -q
    macsyfinder --sequence-db proteins.faa --db-type gembase --replicon-topology linear --models TXSScan all -w ~{threads} --models-dir '~{txsscan_models_dir}' -o macsyfinder > macsyfinder.log 2>&1
    python /opt/bacsec/collect_tsv.py --raw macsyfinder --mapping ~{contig_mapping} --proteins proteins.faa --sample-id '~{sample_id}'
  >>>
  output {
    File systems = "secretion_systems.tsv"
    File genes = "secretion_genes.tsv"
  }
  runtime { docker: docker_image cpu: threads memory: memory_gb + " GB" disks: "local-disk " + disk_gb + " SSD" }
}

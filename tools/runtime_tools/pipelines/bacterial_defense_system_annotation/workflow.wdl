version 1.0

# BacDef: DefenseFinder annotation. The workflow accepts one unified main file
# and uses input_type to select assembled-genome or read-assembly mode.
workflow BacDef {
  input {
    String sample_id
    String input_type
    File file1Path
    File? file2Path
    String defensefinder_models_dir
    String docker_image = "cncb/bacdef:v2"
    Int threads = 8
    Int min_contig_length = 1000
    String genome_context = "auto"
    Int memory_gb = 32
    Int disk_gb = 100
  }
  if (input_type == "genome") { call DefNormalize as Genome { input: fasta = file1Path, sample_id = sample_id, min_contig_length = min_contig_length, docker_image = docker_image } }
  if (input_type == "metagenome") {
    call DefAssemble { input: read1 = file1Path, read2 = file2Path, threads = threads, min_contig_length = min_contig_length, docker_image = docker_image, memory_gb = memory_gb, disk_gb = disk_gb }
    call DefNormalize as Assembly { input: fasta = DefAssemble.contigs, sample_id = sample_id, min_contig_length = min_contig_length, docker_image = docker_image }
  }
  File normalized_fasta = select_first([Genome.normalized_fasta, Assembly.normalized_fasta])
  File contig_mapping = select_first([Genome.contig_mapping, Assembly.contig_mapping])
  String selected_context = if (genome_context == "auto") then (if (input_type == "genome") then "complete" else "metagenome") else genome_context
  call CallDefenseFinder { input: normalized_fasta = normalized_fasta, contig_mapping = contig_mapping, sample_id = sample_id, defensefinder_models_dir = defensefinder_models_dir, threads = threads, prodigal_mode = if (selected_context == "complete") then "single" else "meta", docker_image = docker_image, memory_gb = memory_gb, disk_gb = disk_gb }
  output {
    File defense_systems = CallDefenseFinder.systems
    File defense_genes = CallDefenseFinder.genes
    File defense_hmmer_hits = CallDefenseFinder.hmmer_hits
  }
}
task DefAssemble {
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
  }
  runtime { docker: docker_image cpu: threads memory: memory_gb + " GB" disks: "local-disk " + disk_gb + " SSD" }
}

task DefNormalize {
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
    "${READER[@]}" | awk -v sample="~{sample_id}" -v minlen=~{min_contig_length} 'BEGIN{print "replicon_id\tcontig_id\tlength_bp">"contig_mapping.tsv"} function emit(){if(name!=""&&length(seq)>=minlen){n++;id=sample "C" sprintf("%06d",n);print ">"id>"normalized_contigs.fna";for(i=1;i<=length(seq);i+=80)print substr(seq,i,80)>"normalized_contigs.fna";print id "\t" name "\t" length(seq)>"contig_mapping.tsv"}} /^>/{emit();name=substr($0,2);sub(/[ \t].*/,"",name);seq="";next}{gsub(/[ \t\r]/,"",$0);seq=seq toupper($0)} END{emit();if(n==0)exit 2}'
  >>>
  output {
    File normalized_fasta = "normalized_contigs.fna"
    File contig_mapping = "contig_mapping.tsv"
  }
  runtime { docker: docker_image }
}

task CallDefenseFinder {
  input {
    File normalized_fasta
    File contig_mapping
    String sample_id
    String defensefinder_models_dir
    Int threads
    String prodigal_mode
    String docker_image
    Int memory_gb
    Int disk_gb
  }
  command <<<
    set -euo pipefail
    prodigal -i ~{normalized_fasta} -a proteins.faa -d genes.fna -f gff -o genes.gff -p ~{prodigal_mode} -q
    defense-finder run --db-type gembase --out-dir defensefinder --workers ~{threads} --preserve-raw --models-dir '~{defensefinder_models_dir}' proteins.faa > defensefinder.log 2>&1
    python /opt/bacdef/collect_tsv.py --raw defensefinder --mapping ~{contig_mapping} --sample-id '~{sample_id}'
  >>>
  output {
    File systems = "defense_systems.tsv"
    File genes = "defense_genes.tsv"
    File hmmer_hits = "defense_hmmer_hits.tsv"
  }
  runtime { docker: docker_image cpu: threads memory: memory_gb + " GB" disks: "local-disk " + disk_gb + " SSD" }
}

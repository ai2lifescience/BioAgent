version 1.0

# BacBGC selects antiSMASH for complete genomes and GECCO for assemblies.
workflow BacBGC {
  input {
    String sample_id
    String input_type
    File file1Path
    File? file2Path
    String docker_image = "cncb/bacbgc:v2"
    Int threads = 8
    Int min_contig_length = 1000
    String genome_context = "auto" # auto follows input_type; complete selects antiSMASH
    String bgc_backend = "auto" # auto, gecco, or antismash
    Float gecco_threshold = 0.8
    Int gecco_min_cds = 3
    Int memory_gb = 48
    Int disk_gb = 150
  }
  if (input_type == "genome") { call BgcNormalize as Genome { input: fasta = file1Path, sample_id = sample_id, min_contig_length = min_contig_length, docker_image = docker_image } }
  if (input_type == "metagenome") {
    call BgcAssemble { input: read1 = file1Path, read2 = file2Path, threads = threads, min_contig_length = min_contig_length, docker_image = docker_image, memory_gb = memory_gb, disk_gb = disk_gb }
    call BgcNormalize as Assembly { input: fasta = BgcAssemble.contigs, sample_id = sample_id, min_contig_length = min_contig_length, docker_image = docker_image }
  }
  File normalized_fasta = select_first([Genome.normalized_fasta, Assembly.normalized_fasta])
  File contig_mapping = select_first([Genome.contig_mapping, Assembly.contig_mapping])
  String selected_context = if (genome_context == "auto") then (if (input_type == "genome") then "complete" else "metagenome") else genome_context
  String selected_backend = if (bgc_backend == "auto") then (if (selected_context == "complete") then "antismash" else "gecco") else bgc_backend
  if (selected_backend == "antismash") {
    call RunAntiSMASH { input: normalized_fasta = normalized_fasta, contig_mapping = contig_mapping, sample_id = sample_id, threads = threads, docker_image = docker_image, memory_gb = memory_gb, disk_gb = disk_gb }
  }
  if (selected_backend == "gecco") {
    call RunGECCO { input: normalized_fasta = normalized_fasta, contig_mapping = contig_mapping, sample_id = sample_id, threads = threads, threshold = gecco_threshold, min_cds = gecco_min_cds, docker_image = docker_image, memory_gb = memory_gb, disk_gb = disk_gb }
  }
  output {
    File bgc_clusters = select_first([RunAntiSMASH.clusters, RunGECCO.clusters])
    File bgc_genes = select_first([RunAntiSMASH.genes, RunGECCO.genes])
    File bgc_features = select_first([RunAntiSMASH.features, RunGECCO.features])
  }
}

task BgcAssemble {
  input {
    File read1
    File? read2
    Int threads
    Int min_contig_length
    String docker_image
    Int memory_gb
    Int disk_gb
  }
  # Cromwell evaluates every ~{} while instantiating the command, including the unused shell branch.
  String read2_path = if defined(read2) then select_first([read2]) else ""
  command <<<
    set -euo pipefail
    if [[ -n "~{read2_path}" ]]; then
      fastp -i ~{read1} -I ~{read2_path} -o trimmed_R1.fastq.gz -O trimmed_R2.fastq.gz --thread ~{if (threads < 16) then threads else 16} --json fastp.json --html fastp.html
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

task BgcNormalize {
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

task RunGECCO {
  input {
    File normalized_fasta
    File contig_mapping
    String sample_id
    Int threads
    Float threshold
    Int min_cds
    String docker_image
    Int memory_gb
    Int disk_gb
  }
  command <<<
    set -euo pipefail
    gecco run --genome ~{normalized_fasta} -o gecco --jobs ~{threads} --cds ~{min_cds} --threshold ~{threshold} > gecco.log 2>&1
    python /opt/bacbgc/parse_bgc.py --backend gecco --raw-dir gecco --sample-id '~{sample_id}' --mapping ~{contig_mapping} --fasta ~{normalized_fasta}
  >>>
  output {
    File clusters = "bgc_clusters.tsv"
    File genes = "bgc_genes.tsv"
    File features = "bgc_features.tsv"
  }
  runtime { docker: docker_image cpu: threads memory: memory_gb + " GB" disks: "local-disk " + disk_gb + " SSD" }
}

task RunAntiSMASH {
  input {
    File normalized_fasta
    File contig_mapping
    String sample_id
    Int threads
    String docker_image
    Int memory_gb
    Int disk_gb
  }
  command <<<
    set -euo pipefail
    antismash --taxon bacteria --cpus ~{threads} --output-dir antismash --genefinding-tool prodigal --cb-knownclusters ~{normalized_fasta} > antismash.log 2>&1
    python /opt/bacbgc/parse_bgc.py --backend antismash --raw-dir antismash --sample-id '~{sample_id}' --mapping ~{contig_mapping} --fasta ~{normalized_fasta}
  >>>
  output {
    File clusters = "bgc_clusters.tsv"
    File genes = "bgc_genes.tsv"
    File features = "bgc_features.tsv"
  }
  runtime { docker: docker_image cpu: threads memory: memory_gb + " GB" disks: "local-disk " + disk_gb + " SSD" }
}

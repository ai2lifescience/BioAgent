version 1.0

# Read QC workflow. A workflow run processes one sample; submit one run per
# sample, or use an external WDL launcher to fan out samples.
workflow ReadQc {
  input {
    String sample_id
    File fastq_r1
    File? fastq_r2

    # Adapter trimming is disabled by default. For PE, both adapters are required.
    Boolean remove_adapters = false
    String? adapter_r1
    String? adapter_r2

    # Host removal is disabled by default. Provide exactly one source when it
    # is enabled: a preset host_name or an uploaded host_fasta.
    Boolean remove_host = false
    String? host_name
    # Root containing <host_name>/index.{1,2,3,4,rev.1,rev.2}.bt2[ l ].
    # It must be available inside the task container (baked into the image or
    # mounted through the Cromwell backend configuration).
    String host_index_root = "/data/zhaomh39/program/qc_pipeline/hosts/indexes"
    File? host_fasta

    Int threads = 8
    String trimmomatic_slidingwindow = "4:20"
    Int trimmomatic_leading = 3
    Int trimmomatic_trailing = 3
    Int trimmomatic_minlen = 36
    String host_bowtie2_preset = "--very-sensitive-local"

    # UniVec_Core filtering is optional. The prefix points to existing mounted
    # index files, for example /data/references/UniVec_Core/bowtie2/index.
    Boolean remove_univec = false
    String? univec_index_prefix
    String univec_bowtie2_preset = "--very-sensitive-local"

    String docker_image = "cncb/qc-pipeline:v1.0"
    Int memory_gb = 32
    Int disk_gb = 200
  }

  if (remove_host && defined(host_fasta) && !defined(host_name)) {
    call PrepareHostIndex {
      input:
        host_fasta = host_fasta,
        docker_image = docker_image,
        cpu = threads,
        memory_gb = memory_gb,
        disk_gb = disk_gb
    }
  }

  Array[File] custom_host_indexes = select_first([PrepareHostIndex.host_index_files, []])
  Boolean host_fasta_supplied = defined(host_fasta)

  if (defined(fastq_r2)) {
    call QcPe {
      input:
        sample_id = sample_id,
        fastq_r1 = fastq_r1,
        fastq_r2 = select_first([fastq_r2]),
        remove_adapters = remove_adapters,
        adapter_r1 = adapter_r1,
        adapter_r2 = adapter_r2,
        remove_host = remove_host,
        host_name = host_name,
        host_index_root = host_index_root,
        custom_host_index_files = custom_host_indexes,
        host_fasta_supplied = host_fasta_supplied,
        host_bowtie2_preset = host_bowtie2_preset,
        remove_univec = remove_univec,
        univec_index_prefix = univec_index_prefix,
        univec_bowtie2_preset = univec_bowtie2_preset,
        trimmomatic_slidingwindow = trimmomatic_slidingwindow,
        trimmomatic_leading = trimmomatic_leading,
        trimmomatic_trailing = trimmomatic_trailing,
        trimmomatic_minlen = trimmomatic_minlen,
        threads = threads,
        docker_image = docker_image,
        memory_gb = memory_gb,
        disk_gb = disk_gb
    }
  }

  if (!defined(fastq_r2)) {
    call QcSe {
      input:
        sample_id = sample_id,
        fastq_r1 = fastq_r1,
        remove_adapters = remove_adapters,
        adapter_r1 = adapter_r1,
        remove_host = remove_host,
        host_name = host_name,
        host_index_root = host_index_root,
        custom_host_index_files = custom_host_indexes,
        host_fasta_supplied = host_fasta_supplied,
        host_bowtie2_preset = host_bowtie2_preset,
        remove_univec = remove_univec,
        univec_index_prefix = univec_index_prefix,
        univec_bowtie2_preset = univec_bowtie2_preset,
        trimmomatic_slidingwindow = trimmomatic_slidingwindow,
        trimmomatic_leading = trimmomatic_leading,
        trimmomatic_trailing = trimmomatic_trailing,
        trimmomatic_minlen = trimmomatic_minlen,
        threads = threads,
        docker_image = docker_image,
        memory_gb = memory_gb,
        disk_gb = disk_gb
    }
  }

  File summary_row = select_first([QcPe.summary_row, QcSe.summary_row])
  call CollectQcSummary {
    input:
      summary_rows = [summary_row],
      docker_image = docker_image,
      memory_gb = memory_gb,
      disk_gb = disk_gb
  }
  output {
    File qc_summary = CollectQcSummary.qc_summary
    File? clean_r1 = select_first([QcPe.clean_r1, QcSe.clean_r1])
    File? clean_r2 = QcPe.clean_r2
    # Aggregated FastQC / cutadapt / Trimmomatic / bowtie2 logs (07_multiqc.sh).
    File multiqc_html = select_first([QcPe.multiqc_html, QcSe.multiqc_html])
  }
}

task PrepareHostIndex {
  input {
    File? host_fasta
    String docker_image
    Int cpu
    Int memory_gb
    Int disk_gb
  }
  command <<<
    set -euo pipefail
    fasta='~{if defined(host_fasta) then select_first([host_fasta]) else ""}'
    if [[ -z "$fasta" ]]; then
      echo 'When remove_host=true, host_fasta is required.' >&2
      exit 2
    fi
    cp "$fasta" host.fa
    bowtie2-build --threads ~{cpu} host.fa host_index
  >>>
  output {
    # *.bt2* matches both standard .bt2 and large-index .bt2l files. A single
    # glob avoids Cromwell's MaybeEmptyArrayType concatenation ambiguity.
    Array[File] host_index_files = glob("host_index.*.bt2*")
  }
  runtime {
    docker: docker_image
    cpu: cpu
    memory: "~{memory_gb} GB"
    disks: "local-disk ~{disk_gb} SSD"
  }
}

task QcSe {
  input {
    String sample_id
    File fastq_r1
    Boolean remove_adapters
    String? adapter_r1
    Boolean remove_host
    String? host_name
    String host_index_root
    Array[File] custom_host_index_files
    Boolean host_fasta_supplied
    String host_bowtie2_preset
    Boolean remove_univec
    String? univec_index_prefix
    String univec_bowtie2_preset
    String trimmomatic_slidingwindow
    Int trimmomatic_leading
    Int trimmomatic_trailing
    Int trimmomatic_minlen
    Int threads
    String docker_image
    Int memory_gb
    Int disk_gb
  }
  command <<<
    set -euo pipefail
    # Normalize to real .fastq.gz by magic bytes (1f 8b). Avoids FastQC/trimmomatic
    # treating plain FASTQ that was blindly renamed/symlinked to *.fastq.gz.
    ensure_fastq_gz() {
      local src="$1" dest="$2" magic
      magic=$(od -An -tx1 -N2 -- "$src" | tr -d ' \n')
      if [[ "$magic" == "1f8b" ]]; then
        ln -f -- "$src" "$dest" 2>/dev/null || cp -f -- "$src" "$dest"
      else
        gzip -c -- "$src" > "$dest"
      fi
    }
    count_reads() { gzip -cd -- "$1" | awk 'END { if (NR % 4) exit 2; print NR / 4 }'; }
    ensure_fastq_gz '~{fastq_r1}' input.R1.fastq.gz
    adapter='~{if defined(adapter_r1) then select_first([adapter_r1]) else ""}'
    if ~{remove_adapters}; then
      [[ -n "$adapter" ]] || { echo 'adapter_r1 is required when remove_adapters=true.' >&2; exit 2; }
      cutadapt -j ~{threads} -a "$adapter" -o adapter.fastq.gz input.R1.fastq.gz > cutadapt.log 2>&1
    else
      cp -f input.R1.fastq.gz adapter.fastq.gz
    fi
    mkdir -p raw_fastqc clean_fastqc
    ln -sf input.R1.fastq.gz raw.fastq.gz
    fastqc --threads ~{threads} --outdir raw_fastqc raw.fastq.gz
    trimmomatic SE -threads ~{threads} -phred33 adapter.fastq.gz trimmed.fastq.gz SLIDINGWINDOW:'~{trimmomatic_slidingwindow}' LEADING:~{trimmomatic_leading} TRAILING:~{trimmomatic_trailing} MINLEN:~{trimmomatic_minlen} 2> trimmomatic.log
    if ~{remove_univec}; then
      univec_prefix='~{if defined(univec_index_prefix) then select_first([univec_index_prefix]) else ""}'
      [[ -n "$univec_prefix" ]] || { echo 'univec_index_prefix is required when remove_univec=true.' >&2; exit 2; }
      [[ -f "${univec_prefix}.1.bt2" || -f "${univec_prefix}.1.bt2l" ]] || { echo "UniVec index is unavailable: $univec_prefix" >&2; exit 1; }
      bowtie2 ~{univec_bowtie2_preset} --threads ~{threads} -x "$univec_prefix" -U trimmed.fastq.gz --un-gz univec_clean.fastq.gz -S /dev/null 2> univec_removal.log
    else
      cp trimmed.fastq.gz univec_clean.fastq.gz
    fi
    before_host=$(count_reads univec_clean.fastq.gz)
    host_name='~{if defined(host_name) then select_first([host_name]) else ""}'
    if ~{remove_host}; then
      [[ -z "$host_name" || ~{host_fasta_supplied} = false ]] || { echo 'Provide only one of host_name or host_fasta.' >&2; exit 2; }
      if [[ -n "$host_name" ]]; then
        [[ "$host_name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo 'Invalid host_name.' >&2; exit 2; }
        host_prefix='~{host_index_root}'/"$host_name"/index
      else
        [[ ~{length(custom_host_index_files)} -gt 0 ]] || { echo 'When remove_host=true, provide exactly one of host_name or host_fasta.' >&2; exit 2; }
        host_prefix=host_index
      fi
      bowtie2 ~{host_bowtie2_preset} --threads ~{threads} -x "$host_prefix" -U univec_clean.fastq.gz --un-gz clean.fastq.gz -S /dev/null 2> host_removal.log
    else
      cp univec_clean.fastq.gz clean.fastq.gz
    fi
    fastqc --threads ~{threads} --outdir clean_fastqc clean.fastq.gz
    # 07_multiqc.sh: aggregate tool reports into one HTML.
    mkdir -p multiqc_in
    cp -r raw_fastqc clean_fastqc multiqc_in/
    for f in cutadapt.log trimmomatic.log univec_removal.log host_removal.log; do
      [[ -f "$f" ]] && cp "$f" multiqc_in/
    done
    multiqc -f -o multiqc_out multiqc_in
    raw=$(count_reads input.R1.fastq.gz)
    after_trim=$(count_reads trimmed.fastq.gz)
    final=$(count_reads clean.fastq.gz)
    printf '%s\tSE\t%s\t%s\t%s\t%s\t%s\t%s\n' '~{sample_id}' "$raw" "$((raw-after_trim))" "$((after_trim-before_host))" "$before_host" "$((before_host-final))" "$final" > summary_row.tsv
  >>>
  output {
    File clean_r1 = "clean.fastq.gz"
    File summary_row = "summary_row.tsv"
    File multiqc_html = "multiqc_out/multiqc_report.html"
  }
  runtime { docker: docker_image cpu: threads memory: "~{memory_gb} GB" disks: "local-disk ~{disk_gb} SSD" }
}

task QcPe {
  input {
    String sample_id
    File fastq_r1
    File fastq_r2
    Boolean remove_adapters
    String? adapter_r1
    String? adapter_r2
    Boolean remove_host
    String? host_name
    String host_index_root
    Array[File] custom_host_index_files
    Boolean host_fasta_supplied
    String host_bowtie2_preset
    Boolean remove_univec
    String? univec_index_prefix
    String univec_bowtie2_preset
    String trimmomatic_slidingwindow
    Int trimmomatic_leading
    Int trimmomatic_trailing
    Int trimmomatic_minlen
    Int threads
    String docker_image
    Int memory_gb
    Int disk_gb
  }
  command <<<
    set -euo pipefail
    ensure_fastq_gz() {
      local src="$1" dest="$2" magic
      magic=$(od -An -tx1 -N2 -- "$src" | tr -d ' \n')
      if [[ "$magic" == "1f8b" ]]; then
        ln -f -- "$src" "$dest" 2>/dev/null || cp -f -- "$src" "$dest"
      else
        gzip -c -- "$src" > "$dest"
      fi
    }
    count_reads() { gzip -cd -- "$1" | awk 'END { if (NR % 4) exit 2; print NR / 4 }'; }
    ensure_fastq_gz '~{fastq_r1}' input.R1.fastq.gz
    ensure_fastq_gz '~{fastq_r2}' input.R2.fastq.gz
    adapter1='~{if defined(adapter_r1) then select_first([adapter_r1]) else ""}'
    adapter2='~{if defined(adapter_r2) then select_first([adapter_r2]) else ""}'
    if ~{remove_adapters}; then
      [[ -n "$adapter1" && -n "$adapter2" ]] || { echo 'adapter_r1 and adapter_r2 are required for PE adapter trimming.' >&2; exit 2; }
      cutadapt -j ~{threads} -a "$adapter1" -A "$adapter2" -o adapter.R1.fastq.gz -p adapter.R2.fastq.gz input.R1.fastq.gz input.R2.fastq.gz > cutadapt.log 2>&1
    else
      cp -f input.R1.fastq.gz adapter.R1.fastq.gz
      cp -f input.R2.fastq.gz adapter.R2.fastq.gz
    fi
    mkdir -p raw_fastqc clean_fastqc
    ln -sf input.R1.fastq.gz raw.R1.fastq.gz
    ln -sf input.R2.fastq.gz raw.R2.fastq.gz
    fastqc --threads ~{threads} --outdir raw_fastqc raw.R1.fastq.gz raw.R2.fastq.gz
    trimmomatic PE -threads ~{threads} -phred33 adapter.R1.fastq.gz adapter.R2.fastq.gz trimmed.R1.fastq.gz discarded.R1.fastq.gz trimmed.R2.fastq.gz discarded.R2.fastq.gz SLIDINGWINDOW:'~{trimmomatic_slidingwindow}' LEADING:~{trimmomatic_leading} TRAILING:~{trimmomatic_trailing} MINLEN:~{trimmomatic_minlen} 2> trimmomatic.log
    if ~{remove_univec}; then
      univec_prefix='~{if defined(univec_index_prefix) then select_first([univec_index_prefix]) else ""}'
      [[ -n "$univec_prefix" ]] || { echo 'univec_index_prefix is required when remove_univec=true.' >&2; exit 2; }
      [[ -f "${univec_prefix}.1.bt2" || -f "${univec_prefix}.1.bt2l" ]] || { echo "UniVec index is unavailable: $univec_prefix" >&2; exit 1; }
      bowtie2 ~{univec_bowtie2_preset} --reorder --threads ~{threads} -x "$univec_prefix" -1 trimmed.R1.fastq.gz -2 trimmed.R2.fastq.gz | samtools view -u -f 12 -F 2304 - | samtools collate -f -u -O - | samtools fastq -@ ~{threads} -1 univec_clean.R1.fastq.gz -2 univec_clean.R2.fastq.gz -0 /dev/null -s /dev/null -n - 2> univec_removal.log
    else
      cp trimmed.R1.fastq.gz univec_clean.R1.fastq.gz; cp trimmed.R2.fastq.gz univec_clean.R2.fastq.gz
    fi
    before_host=$(count_reads univec_clean.R1.fastq.gz)
    host_name='~{if defined(host_name) then select_first([host_name]) else ""}'
    if ~{remove_host}; then
      [[ -z "$host_name" || ~{host_fasta_supplied} = false ]] || { echo 'Provide only one of host_name or host_fasta.' >&2; exit 2; }
      if [[ -n "$host_name" ]]; then
        [[ "$host_name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo 'Invalid host_name.' >&2; exit 2; }
        host_prefix='~{host_index_root}'/"$host_name"/index
      else
        [[ ~{length(custom_host_index_files)} -gt 0 ]] || { echo 'When remove_host=true, provide exactly one of host_name or host_fasta.' >&2; exit 2; }
        host_prefix=host_index
      fi
      bowtie2 ~{host_bowtie2_preset} --reorder --threads ~{threads} -x "$host_prefix" -1 univec_clean.R1.fastq.gz -2 univec_clean.R2.fastq.gz 2> host_removal.log | samtools view -u -f 12 -F 2304 - | samtools collate -f -u -O - | samtools fastq -@ ~{threads} -1 clean.R1.fastq.gz -2 clean.R2.fastq.gz -0 /dev/null -s /dev/null -n -
    else
      cp univec_clean.R1.fastq.gz clean.R1.fastq.gz; cp univec_clean.R2.fastq.gz clean.R2.fastq.gz
    fi
    fastqc --threads ~{threads} --outdir clean_fastqc clean.R1.fastq.gz clean.R2.fastq.gz
    # 07_multiqc.sh: aggregate tool reports into one HTML.
    mkdir -p multiqc_in
    cp -r raw_fastqc clean_fastqc multiqc_in/
    for f in cutadapt.log trimmomatic.log univec_removal.log host_removal.log; do
      [[ -f "$f" ]] && cp "$f" multiqc_in/
    done
    multiqc -f -o multiqc_out multiqc_in
    raw=$(count_reads input.R1.fastq.gz); raw_r2=$(count_reads input.R2.fastq.gz); after_trim=$(count_reads trimmed.R1.fastq.gz); final=$(count_reads clean.R1.fastq.gz)
    [[ "$raw" -eq "$raw_r2" ]] || { echo 'Raw PE mate counts differ.' >&2; exit 2; }
    printf '%s\tPE\t%s\t%s\t%s\t%s\t%s\t%s\n' '~{sample_id}' "$raw" "$((raw-after_trim))" "$((after_trim-before_host))" "$before_host" "$((before_host-final))" "$final" > summary_row.tsv
  >>>
  output {
    File clean_r1 = "clean.R1.fastq.gz"
    File clean_r2 = "clean.R2.fastq.gz"
    File summary_row = "summary_row.tsv"
    File multiqc_html = "multiqc_out/multiqc_report.html"
  }
  runtime { docker: docker_image cpu: threads memory: "~{memory_gb} GB" disks: "local-disk ~{disk_gb} SSD" }
}

task CollectQcSummary {
  input {
    Array[File] summary_rows
    String docker_image
    Int memory_gb
    Int disk_gb
  }
  command <<<
    set -euo pipefail
    printf 'sample\tlayout\traw_reads\tquality_dropped_reads\tunivec_core_hit_reads\treads_before_host\thost_reads\tfinal_clean_reads\n' > qc_summary.tsv
    cat ~{sep=' ' summary_rows} >> qc_summary.tsv
  >>>
  output { File qc_summary = "qc_summary.tsv" }
  runtime { docker: docker_image memory: "~{memory_gb} GB" disks: "local-disk ~{disk_gb} SSD" }
}

version 1.0

# Single-sample Metax 0.9.23-beta profiling.
# metax and maCMD come from the Docker image (wdl/Dockerfile).
# Index and databases are prepared outside this workflow. Every input
# path is a String; Cromwell must bind-mount those host paths
# (see wdl/cromwell.local.conf). Output prefix is taken from the reads filename.

workflow metax {
  input {
    String reads
    String? reads2

    # Absolute path to the Metax database JSON (e.g. metax_db.json).
    String db

    # Absolute path to NCBI taxdump (nodes.dmp, names.dmp, merged.dmp).
    String? dmp_dir

    String sequencer = "Illumina"
    String mode = "default"
    Boolean strain = false
    Boolean lowbiomass = false
    Boolean genus_fallback = false
    Boolean strict = false
    Boolean keep_raw = false
    Boolean compress_sam = false
    Boolean by_aligned = false
    Boolean resume = false

    String? reuse_sam
    String? pathogen_host
    String? host

    Float? identity
    Int? mapped_len
    Float? fraction
    Float? min_breadth
    Float? min_cbreadth
    Int? min_reads
    Float? min_oebr
    Float? min_coebr

    Int threads = 20
    Int memory_gb = 64
    Int disk_gb = 100
    String docker = "metax:0.9.23-beta"
  }

  String in_seq = if defined(reads2) then reads + "," + select_first([reads2]) else reads
  Boolean is_paired = defined(reads2)

  call MetaxProfile {
    input:
      reads = reads,
      in_seq = in_seq,
      is_paired = is_paired,
      db = db,
      dmp_dir = dmp_dir,
      sequencer = sequencer,
      mode = mode,
      strain = strain,
      lowbiomass = lowbiomass,
      genus_fallback = genus_fallback,
      strict = strict,
      keep_raw = keep_raw,
      compress_sam = compress_sam,
      by_aligned = by_aligned,
      resume = resume,
      reuse_sam = reuse_sam,
      pathogen_host = pathogen_host,
      host = host,
      identity = identity,
      mapped_len = mapped_len,
      fraction = fraction,
      min_breadth = min_breadth,
      min_cbreadth = min_cbreadth,
      min_reads = min_reads,
      min_oebr = min_oebr,
      min_coebr = min_coebr,
      threads = threads,
      memory_gb = memory_gb,
      disk_gb = disk_gb,
      docker = docker
  }

  output {
    File profile = MetaxProfile.profile
  }
}

task MetaxProfile {
  input {
    String reads
    String in_seq
    Boolean is_paired
    String db
    String? dmp_dir
    String sequencer
    String mode
    Boolean strain
    Boolean lowbiomass
    Boolean genus_fallback
    Boolean strict
    Boolean keep_raw
    Boolean compress_sam
    Boolean by_aligned
    Boolean resume
    String? reuse_sam
    String? pathogen_host
    String? host
    Float? identity
    Int? mapped_len
    Float? fraction
    Float? min_breadth
    Float? min_cbreadth
    Int? min_reads
    Float? min_oebr
    Float? min_coebr
    Int threads
    Int memory_gb
    Int disk_gb
    String docker
  }

  command <<<
    set -eo pipefail

    metax --version
    if [[ -z "~{select_first([reuse_sam, ""])}" ]] && ! command -v maCMD >/dev/null 2>&1; then
      echo "maCMD not found in the image. Rebuild with wdl/Dockerfile." >&2
      exit 1
    fi

    prefix=$(basename "~{reads}")
    prefix=$(printf '%s\n' "$prefix" | sed -E 's/\.gz$//; s/\.(fastq|fq|fasta|fa)$//; s/(_R1|_1)$//')
    echo "$prefix" > prefix.txt

    set -- metax profile --db "~{db}" -i "~{in_seq}" -o "$prefix" --sequencer "~{sequencer}" --mode "~{mode}" -t ~{threads}
    ~{if defined(dmp_dir) then "set -- \"$@\" --dmp-dir \"" + select_first([dmp_dir]) + "\"" else ""}
    ~{if is_paired then "set -- \"$@\" -p" else ""}
    ~{if strain then "set -- \"$@\" --strain" else ""}
    ~{if lowbiomass then "set -- \"$@\" --lowbiomass" else ""}
    ~{if genus_fallback then "set -- \"$@\" --genus-fallback" else ""}
    ~{if strict then "set -- \"$@\" --strict" else ""}
    ~{if keep_raw then "set -- \"$@\" --keep-raw" else ""}
    ~{if compress_sam then "set -- \"$@\" --compress-sam" else ""}
    ~{if by_aligned then "set -- \"$@\" --by-aligned" else ""}
    ~{if resume then "set -- \"$@\" --resume" else ""}
    ~{if defined(reuse_sam) then "set -- \"$@\" --reuse-sam \"" + select_first([reuse_sam]) + "\"" else ""}
    ~{if defined(pathogen_host) then "set -- \"$@\" --pathogen-host \"" + select_first([pathogen_host]) + "\"" else ""}
    ~{if defined(host) then "set -- \"$@\" --host \"" + select_first([host]) + "\"" else ""}
    ~{if defined(identity) then "set -- \"$@\" --identity \"" + select_first([identity]) + "\"" else ""}
    ~{if defined(mapped_len) then "set -- \"$@\" --mapped-len \"" + select_first([mapped_len]) + "\"" else ""}
    ~{if defined(fraction) then "set -- \"$@\" --fraction \"" + select_first([fraction]) + "\"" else ""}
    ~{if defined(min_breadth) then "set -- \"$@\" --min-breadth \"" + select_first([min_breadth]) + "\"" else ""}
    ~{if defined(min_cbreadth) then "set -- \"$@\" --min-cbreadth \"" + select_first([min_cbreadth]) + "\"" else ""}
    ~{if defined(min_reads) then "set -- \"$@\" --min-reads \"" + select_first([min_reads]) + "\"" else ""}
    ~{if defined(min_oebr) then "set -- \"$@\" --min-oebr \"" + select_first([min_oebr]) + "\"" else ""}
    ~{if defined(min_coebr) then "set -- \"$@\" --min-coebr \"" + select_first([min_coebr]) + "\"" else ""}
    "$@"

    ls -lh "$prefix".* || true
  >>>

  output {
    File profile = glob("*.profile.txt")[0]
  }

  runtime {
    cpu: threads
    memory: "~{memory_gb} GiB"
    disks: "local-disk ~{disk_gb} HDD"
    docker: docker
  }
}

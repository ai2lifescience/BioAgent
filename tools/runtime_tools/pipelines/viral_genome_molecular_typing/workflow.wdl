version 1.0

workflow run_molecular_typing {
input {
    String pathogen
    String sample
    File input_fasta
    Array[File] REF
    Array[File] NEXTCLADE_DATASET
    String THREADS
    String? HA_REFNAME
    String? REFNAME
    Int? EXPECTED_LEN
    Int? task_cpu
    String docker_image = "molecular-wdl:latest"
}

Int expected_len_sars = select_first([EXPECTED_LEN, 29903])

call GenomicNormalizeFasta {
    input:
    input_fasta = input_fasta,
    sample = sample,
    task_cpu = task_cpu,
    docker_image = docker_image
}

call GenomicFaidxBwaMemExtract {
    input:
    normalized_fasta = GenomicNormalizeFasta.normalized_fasta,
    ref = REF,
    sample = sample,
    threads = THREADS,
    pathogen = pathogen,
    ha_refname = HA_REFNAME,
    refname = REFNAME,
    task_cpu = task_cpu,
    docker_image = docker_image
}

call GenomicNextclade {
    input:
    consensus_fa = GenomicFaidxBwaMemExtract.out_fasta,
    dataset = NEXTCLADE_DATASET,
    sample = sample,
    threads = THREADS,
    pathogen = pathogen,
    task_cpu = task_cpu,
    docker_image = docker_image
}

call GenomicSummarize {
    input:
    pathogen = pathogen,
    nextclade_tsv = GenomicNextclade.nextclade_tsv,
    out_fasta = GenomicFaidxBwaMemExtract.out_fasta,
    expected_len_sars = expected_len_sars,
    sample = sample,
    task_cpu = task_cpu,
    docker_image = docker_image
}

output {
    File result_csv = GenomicSummarize.result_csv
    File nextclade_tsv = GenomicNextclade.nextclade_tsv
    File nextclade_json = GenomicNextclade.nextclade_json
    File ha_or_consensus_fa = GenomicFaidxBwaMemExtract.out_fasta
}
}

task GenomicNormalizeFasta {
input {
    String docker_image
    File input_fasta
    String sample
    Int? task_cpu
}
Int effective_cpu = select_first([task_cpu, 4])
command <<<
    set -euo pipefail
    IN="~{input_fasta}"
    case "$IN" in
    *.gz) gzip -dc "$IN" > "~{sample}.input.fasta" ;;
    *) cp "$IN" "~{sample}.input.fasta" ;;
    esac
    test -s "~{sample}.input.fasta"
>>>
output {
    File normalized_fasta = "~{sample}.input.fasta"
}
runtime {
    docker: docker_image
    cpu: effective_cpu
    memory: "4 GB"
}
}

task GenomicFaidxBwaMemExtract {
input {
    String docker_image
    File normalized_fasta
    Array[File] ref
    String sample
    String threads
    String pathogen
    String? ha_refname
    String? refname
    Int? task_cpu
}
Int effective_cpu = select_first([task_cpu, 8])
command <<<
    set -euo pipefail
    P="$(echo "~{pathogen}" | tr '[:lower:]' '[:upper:]' | tr '-' '_')"
    case "$P" in
    SARS_COV_2|SARS_COV2|SARSCOV2|SC2)
        SEG="~{if defined(refname) then refname else ""}"
        ;;
    *)
        SEG="~{if defined(ha_refname) then ha_refname else ""}"
        ;;
    esac
    OUT_FN="~{sample}_HA_consensus.fa"
    test -n "$SEG" || { echo "ERROR: set HA_REFNAME or REFNAME according to pathogen" >&2; exit 1; }
    REF_FASTA=""
    for f in ~{sep=' ' ref}; do
        bn="$(basename "$f")"
        case "$bn" in
        *.fna|*.fa|*.fasta)
            if [ -z "$REF_FASTA" ]; then REF_FASTA="$f"; fi
            ;;
        esac
    done
    test -n "$REF_FASTA" && test -s "$REF_FASTA" || { echo "ERROR: no reference FASTA found in REF array" >&2; exit 1; }
    if [ ! -s "${REF_FASTA}.bwt" ]; then
        echo "[GenomicFaidxBwaMemExtract] No BWA index (${REF_FASTA}.bwt); running bwa index..."
        bwa index "$REF_FASTA"
    fi
    if [ ! -s "${REF_FASTA}.fai" ]; then
        echo "[GenomicFaidxBwaMemExtract] No samtools index (${REF_FASTA}.fai); running samtools faidx..."
        samtools faidx "$REF_FASTA"
    fi
    SELECTED_QUERY="selected_query.txt"
    BWA=bwa
    BS="$(awk 'BEGIN { printf "%c", 92 }')"
    RG_HDR="@RG${BS}tID:~{sample}${BS}tSM:~{sample}${BS}tPL:ILLUMINA"

    select_best_query() {
    local input_fasta="$1"
    "$BWA" mem -t ~{threads} -k 15 -a -R "$RG_HDR" \
        "$REF_FASTA" "$input_fasta" | awk -v ref_seg="$SEG" '
        function cigar_ref_len(cigar,   i, c, num, len) {
            len = 0
            num = ""
            for (i = 1; i <= length(cigar); i++) {
                c = substr(cigar, i, 1)
                if (c ~ /[0-9]/) {
                    num = num c
                } else {
                    if (c == "M" || c == "=" || c == "X") {
                        len += num + 0
                    }
                    num = ""
                }
            }
            return len
        }
        function cigar_query_start(cigar,   i, c, num, started, start) {
            start = 1
            num = ""
            started = 0
            for (i = 1; i <= length(cigar); i++) {
                c = substr(cigar, i, 1)
                if (c ~ /[0-9]/) {
                    num = num c
                } else {
                    if (!started && c == "S") {
                        start += num + 0
                    } else if (c == "M" || c == "=" || c == "X" || c == "I" || c == "D" || c == "N") {
                        started = 1
                    }
                    num = ""
                }
            }
            return start
        }
        function cigar_query_len(cigar,   i, c, num, len) {
            len = 0
            num = ""
            for (i = 1; i <= length(cigar); i++) {
                c = substr(cigar, i, 1)
                if (c ~ /[0-9]/) {
                    num = num c
                } else {
                    if (c == "M" || c == "=" || c == "X" || c == "I") {
                        len += num + 0
                    }
                    num = ""
                }
            }
            return len
        }
        $0 !~ /^@/ && $3 != "*" && $3 == ref_seg {
            qname = $1
            flag = $2 + 0
            mapq = $5 + 0
            cigar = $6
            aln_len = cigar_ref_len(cigar)
            qstart = cigar_query_start(cigar)
            qlen = cigar_query_len(cigar)
            rev = (int(flag / 16) % 2)
            as = 0
            for (i = 12; i <= NF; i++) {
                if ($i ~ /^AS:i:/) {
                    split($i, a, ":")
                    as = a[3] + 0
                }
            }
            score = aln_len * 1000000 + mapq * 1000 + as
            if (score > best_score || (score == best_score && aln_len > best_len)) {
                best_score = score
                best_len = aln_len
                best_qname = qname
                best_qstart = qstart
                best_qlen = qlen
                best_rev = rev
            }
        }
        END {
            if (best_qname != "") {
                print best_qname "\t" best_qstart "\t" best_qlen "\t" best_rev
                exit 0
            }
            exit 1
        }'
    }

    write_trimmed_record() {
    local input_fasta="$1"
    local output_fasta="$2"
    local target_name="$3"
    local start_pos="$4"
    local trim_len="$5"
    local is_reverse="$6"
    awk -v target="$target_name" -v start="$start_pos" -v len="$trim_len" -v rev="$is_reverse" -v out="$output_fasta" '
    BEGIN {
        nl = sprintf("%c", 10)
        FS = nl
        RS = ">"
        ORS = ""
        found = 0
    }
    function comp(c) {
        c = toupper(c)
        if (c == "A") return "T"
        if (c == "T") return "A"
        if (c == "G") return "C"
        if (c == "C") return "G"
        return "N"
    }
    function revcomp(s,   i, out, c) {
        out = ""
        for (i = length(s); i >= 1; i--) {
            c = substr(s, i, 1)
            out = out comp(c)
        }
        return out
    }
    NR > 1 {
        record = $0
        header = record
        seq = record
        sub(nl ".*", "", header)
        sub("^[^" nl "]*" nl, "", seq)
        gsub(nl, "", seq)
        split(header, h, /[ \t]/)
        if (h[1] == target) {
            if (start < 1) start = 1
            if (len > 0) {
                subseq = substr(seq, start, len)
                if (rev == 1) {
                    subseq = revcomp(subseq)
                }
                print ">" target nl subseq nl > out
            } else {
                print ">" target nl seq nl > out
            }
            found = 1
            exit 0
        }
    }
    END {
        if (found == 0) exit 1
    }' "$input_fasta"
    }

    if select_best_query "~{normalized_fasta}" > "$SELECTED_QUERY"; then
    SELECTED_QUERY_NAME=$(awk -F'\t' '{print $1}' "$SELECTED_QUERY")
    SELECTED_START=$(awk -F'\t' '{print $2}' "$SELECTED_QUERY")
    SELECTED_LEN=$(awk -F'\t' '{print $3}' "$SELECTED_QUERY")
    SELECTED_REV=$(awk -F'\t' '{print $4}' "$SELECTED_QUERY")
    write_trimmed_record "~{normalized_fasta}" "$OUT_FN" "$SELECTED_QUERY_NAME" "$SELECTED_START" "$SELECTED_LEN" "$SELECTED_REV"
    else
    echo "ERROR: could not extract a usable sequence from input FASTA via reference alignment" >&2
    exit 1
    fi
    sed -i.bak "1s/^>.*/>~{sample}/" "$OUT_FN"
    rm -f "${OUT_FN}.bak"
>>>
output {
    File out_fasta = "~{sample}_HA_consensus.fa"
}
runtime {
    docker: docker_image
    cpu: effective_cpu
    memory: "16 GB"
}
}

task GenomicNextclade {
input {
    String docker_image
    File consensus_fa
    Array[File] dataset
    String sample
    String threads
    String pathogen
    Int? task_cpu
}
Int effective_cpu = select_first([task_cpu, 8])
command <<<
    set -euo pipefail
    INPUT_REF=""
    INPUT_ANNOTATION=""
    INPUT_TREE=""
    INPUT_PATHOGEN_JSON=""
    for f in ~{sep=' ' dataset}; do
        bn="$(basename "$f")"
        case "$bn" in
        pathogen.json)
            INPUT_PATHOGEN_JSON="$f"
            ;;
        tree.json)
            INPUT_TREE="$f"
            ;;
        genome_annotation.gff3|genemap.gff)
            INPUT_ANNOTATION="$f"
            ;;
        reference.fasta|ref.fasta)
            INPUT_REF="$f"
            ;;
        *.gff3)
            if [ -z "$INPUT_ANNOTATION" ]; then INPUT_ANNOTATION="$f"; fi
            ;;
        *.fasta|*.fa|*.fna)
            if [ -z "$INPUT_REF" ]; then INPUT_REF="$f"; fi
            ;;
        esac
    done
    test -n "$INPUT_REF" && test -s "$INPUT_REF" || {
        echo "ERROR: NEXTCLADE_DATASET must include reference.fasta for --input-ref" >&2
        exit 1
    }
    NC_ARGS=(--input-ref "$INPUT_REF")
    if [ -n "$INPUT_ANNOTATION" ] && [ -s "$INPUT_ANNOTATION" ]; then
        NC_ARGS+=(--input-annotation "$INPUT_ANNOTATION")
    fi
    if [ -n "$INPUT_TREE" ] && [ -s "$INPUT_TREE" ]; then
        NC_ARGS+=(--input-tree "$INPUT_TREE")
    fi
    if [ -n "$INPUT_PATHOGEN_JSON" ] && [ -s "$INPUT_PATHOGEN_JSON" ]; then
        NC_ARGS+=(--input-pathogen-json "$INPUT_PATHOGEN_JSON")
    fi
    nextclade run "~{consensus_fa}" \
    "${NC_ARGS[@]}" \
    --output-json "~{sample}_nextclade.json" \
    --output-tsv "~{sample}_nextclade.tsv" \
    --jobs ~{threads}
>>>
output {
    File nextclade_json = "~{sample}_nextclade.json"
    File nextclade_tsv = "~{sample}_nextclade.tsv"
}
runtime {
    docker: docker_image
    cpu: effective_cpu
    memory: "8 GB"
}
}

task GenomicSummarize {
input {
    String docker_image
    String pathogen
    File nextclade_tsv
    File out_fasta
    Int expected_len_sars
    String sample
    Int? task_cpu
}
Int effective_cpu = select_first([task_cpu, 2])
command <<<
    set -euo pipefail
    TSV="~{nextclade_tsv}"
    FA="~{out_fasta}"
    P="$(echo "~{pathogen}" | tr '[:lower:]' '[:upper:]' | tr '-' '_')"
    case "$P" in
    H1N1)
        SEQ_NAME=$(awk -F"\t" 'NR==2 {print $2}' "$TSV")
        CLADE=$(awk -F"\t" 'NR==2 {print $3}' "$TSV")
        SUBCLADE=$(awk -F"\t" 'NR==2 {print $5}' "$TSV")
        LEGACY_CLADE=$(awk -F"\t" 'NR==2 {print $7}' "$TSV")
        QC_STATUS=$(awk -F"\t" 'NR==2 {print $10}' "$TSV")
        TOTAL_MISSING=$(awk -F"\t" 'NR==2 {print $15}' "$TSV")
        SEQ_LEN=$(awk 'BEGIN{seq=""} /^>/ {next} {seq=seq $0} END {print length(seq)}' "$FA")
        if [ -n "$TOTAL_MISSING" ] && [ "$TOTAL_MISSING" -eq "$TOTAL_MISSING" ] 2>/dev/null; then
        COVERAGE=$(awk -v len="$SEQ_LEN" -v miss="$TOTAL_MISSING" 'BEGIN { if (len > 0) printf "%.2f", (len-miss)/len*100; else print "N/A" }')
        else
        COVERAGE="N/A"
        fi
        FAILED=false
        if [ -z "$SEQ_NAME" ] || [ "$SEQ_NAME" = "" ]; then FAILED=true
        elif [ "$LEGACY_CLADE" = "unassigned" ] || [ "$LEGACY_CLADE" = "" ]; then FAILED=true
        elif [ -n "$TOTAL_MISSING" ] && [ "$TOTAL_MISSING" -gt 1100 ]; then FAILED=true
        fi
        echo "sequence_name,clade,subclade,legacy-clade,quality,coverage,ha_length" > "~{sample}_result.csv"
        if [ "$FAILED" = true ]; then echo "${SEQ_NAME},Fail" >> "~{sample}_result.csv"
        else echo "${SEQ_NAME},${CLADE},${SUBCLADE},${LEGACY_CLADE},${QC_STATUS},${COVERAGE},${SEQ_LEN}" >> "~{sample}_result.csv"
        fi
        ;;
    H3N2)
        SEQ_NAME=$(awk -F"\t" 'NR==2 {print $2}' "$TSV")
        CLADE=$(awk -F"\t" 'NR==2 {print $3}' "$TSV")
        SUBCLADE=$(awk -F"\t" 'NR==2 {print $6}' "$TSV")
        LEGACY_CLADE=$(awk -F"\t" 'NR==2 {print $7}' "$TSV")
        QC_STATUS=$(awk -F"\t" 'NR==2 {print $11}' "$TSV")
        TOTAL_MISSING=$(awk -F"\t" 'NR==2 {print $16}' "$TSV")
        SEQ_LEN=$(awk 'BEGIN{seq=""} /^>/ {next} {seq=seq $0} END {print length(seq)}' "$FA")
        if [ -n "$TOTAL_MISSING" ] && [ "$TOTAL_MISSING" -eq "$TOTAL_MISSING" ] 2>/dev/null; then
        COVERAGE=$(awk -v len="$SEQ_LEN" -v miss="$TOTAL_MISSING" 'BEGIN { if (len > 0) printf "%.2f", (len-miss)/len*100; else print "N/A" }')
        else
        COVERAGE="N/A"
        fi
        FAILED=false
        if [ -z "$SEQ_NAME" ] || [ "$SEQ_NAME" = "" ]; then FAILED=true
        elif [ "$LEGACY_CLADE" = "unassigned" ] || [ "$LEGACY_CLADE" = "" ]; then FAILED=true
        elif [ -n "$TOTAL_MISSING" ] && [ "$TOTAL_MISSING" -gt 1100 ]; then FAILED=true
        fi
        echo "sequence_name,clade,subclade,legacy-clade,quality,coverage,ha_length" > "~{sample}_result.csv"
        if [ "$FAILED" = true ]; then echo "${SEQ_NAME},Fail" >> "~{sample}_result.csv"
        else echo "${SEQ_NAME},${CLADE},${SUBCLADE},${LEGACY_CLADE},${QC_STATUS},${COVERAGE},${SEQ_LEN}" >> "~{sample}_result.csv"
        fi
        ;;
    *)
        EXP=~{expected_len_sars}
        SEQ_NAME=$(awk -F"\t" 'NR==2 {print $2}' "$TSV")
        CLADE=$(awk -F"\t" 'NR==2 {print $4}' "$TSV")
        LINEAGE=$(awk -F"\t" 'NR==2 {print $7}' "$TSV")
        PANGO=$(awk -F"\t" 'NR==2 {print $8}' "$TSV")
        QC_STATUS=$(awk -F"\t" 'NR==2 {print $10}' "$TSV")
        TOTAL_MISSING=$(awk -F"\t" 'NR==2 {print $15}' "$TSV")
        CONS_LEN=$(awk 'BEGIN{seq=""} /^>/ {next} {seq=seq $0} END {print length(seq)}' "$FA")
        if [ -n "$TOTAL_MISSING" ] && [ "$TOTAL_MISSING" -eq "$TOTAL_MISSING" ] 2>/dev/null; then
        COVERAGE=$(awk -v len="$CONS_LEN" -v miss="$TOTAL_MISSING" -v expected="$EXP" 'BEGIN { if (expected > 0) printf "%.2f", (expected-miss)/expected*100; else print "N/A" }')
        else
        COVERAGE="N/A"
        fi
        FAILED=false
        if [ -z "$SEQ_NAME" ] || [ "$SEQ_NAME" = "" ]; then FAILED=true
        elif [ "$CLADE" = "" ] || [ "$CLADE" = "NA" ]; then FAILED=true
        elif [ "$QC_STATUS" = "" ]; then FAILED=true
        elif [ -n "$TOTAL_MISSING" ] && [ "$TOTAL_MISSING" -gt 10000 ]; then FAILED=true
        fi
        echo "sequence_name,clade,lineage,pango,quality,coverage,length" > "~{sample}_result.csv"
        if [ "$FAILED" = true ]; then echo "${SEQ_NAME},Fail" >> "~{sample}_result.csv"
        else echo "${SEQ_NAME},${CLADE},${LINEAGE},${PANGO},${QC_STATUS},${COVERAGE},${CONS_LEN}" >> "~{sample}_result.csv"
        fi
        ;;
    esac
>>>
output {
    File result_csv = "~{sample}_result.csv"
}
runtime {
    docker: docker_image
    cpu: effective_cpu
    memory: "1 GB"
}
}

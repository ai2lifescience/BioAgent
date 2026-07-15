version 1.0

# WDL 1.0: compatible with older Cromwell / validators (no workflow-level if / None)
# Branching is implemented in bash inside MetaAlignUnified and MetaTypingPostTrim

workflow run_molecular_typing {
input {
	String? type
	File file1Path
	File? file2Path
	String sample
	String pathogen
	Array[File] REF
	Array[File] NEXTCLADE_DATASET
	String MIN_LENGTH
	String MIN_QUAL
	String? HA_REFNAME
	String THREADS
	Int? task_cpu
	String docker_image
	String? EXPECTED_LEN
	String? REFNAME
}

Boolean paired = defined(file2Path)

call MetaFastp {
	input:
	docker_image = docker_image,
	file1 = file1Path,
	file2 = file2Path,
	min_length = MIN_LENGTH,
	min_qual = MIN_QUAL,
	threads = THREADS,
	paired = paired,
	task_cpu = task_cpu
}

call MetaAlignUnified {
	input:
	docker_image = docker_image,
	ref = REF,
	clean_r1 = MetaFastp.clean_r1,
	clean_r2 = MetaFastp.clean_r2,
	sample = sample,
	threads = THREADS,
	paired = paired,
	pathogen = pathogen,
	task_cpu = task_cpu
}

call MetaTrim3Bam {
	input:
	docker_image = docker_image,
	final_bam = MetaAlignUnified.final_bam,
	final_bam_bai = MetaAlignUnified.final_bam_bai,
	sample = sample,
	threads = THREADS,
	task_cpu = task_cpu
}

call MetaTypingPostTrim {
	input:
	docker_image = docker_image,
	trim3_bam = MetaTrim3Bam.trim3_bam,
	trim3_bai = MetaTrim3Bam.trim3_bai,
	ref = REF,
	dataset = NEXTCLADE_DATASET,
	sample = sample,
	threads = THREADS,
	pathogen = pathogen,
	ha_refname = HA_REFNAME,
	task_cpu = task_cpu
}

output {
	File result_csv = MetaTypingPostTrim.result_csv
	File nextclade_tsv = MetaTypingPostTrim.nextclade_tsv
	File nextclade_json = MetaTypingPostTrim.nextclade_json
	File consensus_fa = MetaTypingPostTrim.consensus_fa
	File final_bam_out = MetaAlignUnified.final_bam
}
}

task MetaFastp {
input {
	String docker_image
	File file1
	File? file2
	String min_length
	String min_qual
	String threads
	Boolean paired
	Int? task_cpu
}
Int effective_cpu = select_first([task_cpu, 8])
command <<<
	set -euo pipefail
	mkdir -p out
	if [ "~{paired}" = "true" ]; then
	fastp -i "~{file1}" -I "~{file2}" -o out/clean_R1.fastq.gz -O out/clean_R2.fastq.gz \
		--length_required ~{min_length} \
		--cut_front --cut_tail --cut_mean_quality ~{min_qual} \
		--thread ~{threads}
	else
	fastp -i "~{file1}" -o out/clean_R1.fastq.gz \
		--length_required ~{min_length} \
		--cut_front --cut_tail --cut_mean_quality ~{min_qual} \
		--thread ~{threads}
	touch out/clean_R2.fastq.gz
	fi
>>>
output {
	File clean_r1 = "out/clean_R1.fastq.gz"
	File clean_r2 = "out/clean_R2.fastq.gz"
}
runtime {
	docker: docker_image
	cpu: effective_cpu
	memory: "16 GB"
}
}

task MetaAlignUnified {
input {
	String docker_image
	Array[File] ref
	File clean_r1
	File clean_r2
	String sample
	String threads
	Boolean paired
	String pathogen
	Int? task_cpu
}
Int effective_cpu = select_first([task_cpu, 8])
command <<<
	set -euo pipefail
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
	# Cromwell localizes a single FASTA; pre-built .bwt/.fai on the host are not copied — build if missing
	if [ ! -s "${REF_FASTA}.bwt" ]; then
	echo "[MetaAlignUnified] No BWA index (${REF_FASTA}.bwt); running bwa index (large refs may take minutes)..."
	bwa index "$REF_FASTA"
	fi
	if [ ! -s "${REF_FASTA}.fai" ]; then
	echo "[MetaAlignUnified] Running samtools faidx for mpileup..."
	samtools faidx "$REF_FASTA"
	fi
	# BWA -R needs literal \\t (backslash+t). Avoid \\x in WDL so pasted/Python triple-strings do not mangle escapes.
	BS="$(awk 'BEGIN { printf "%c", 92 }')"
	RG="@RG${BS}tID:~{sample}${BS}tSM:~{sample}${BS}tPL:ILLUMINA"
	P="$(echo "~{pathogen}" | tr '[:lower:]' '[:upper:]' | tr '-' '_')"
	case "$P" in
	H3N2)
		command -v java >/dev/null 2>&1 || { echo "ERROR: H3N2 pipeline requires java" >&2; exit 1; }
		if [ "~{paired}" = "true" ]; then
		bwa mem -t ~{threads} -k 15 -R "$RG" "$REF_FASTA" "~{clean_r1}" "~{clean_r2}" | \
			samtools view -Sb - | samtools sort -@ ~{threads} -o sorted.bam
		else
		bwa mem -t ~{threads} -k 15 -R "$RG" "$REF_FASTA" "~{clean_r1}" | \
			samtools view -Sb - | samtools sort -@ ~{threads} -o sorted.bam
		fi
		samtools view -F 4 -q 20 -b sorted.bam > q20.bam
		samtools markdup -s -@ ~{threads} q20.bam dedup.bam
		rm -f sorted.bam q20.bam
		samtools view -F 256 -b dedup.bam > "~{sample}.final.bam"
		samtools index "~{sample}.final.bam"
		rm -f dedup.bam
		;;
	*)
		if [ "~{paired}" = "true" ]; then
		bwa mem -t ~{threads} -k 15 -R "$RG" "$REF_FASTA" "~{clean_r1}" "~{clean_r2}" | \
			samtools fixmate -m - - | samtools sort -@ ~{threads} -o sorted.bam
		else
		bwa mem -t ~{threads} -k 15 -R "$RG" "$REF_FASTA" "~{clean_r1}" | \
			samtools fixmate -m - - | samtools sort -@ ~{threads} -o sorted.bam
		fi
		samtools markdup -s -@ ~{threads} sorted.bam dedup.bam
		samtools view -F 260 -q 20 -b dedup.bam > "~{sample}.final.bam"
		samtools index "~{sample}.final.bam"
		rm -f sorted.bam dedup.bam
		;;
	esac
>>>
output {
	File final_bam = "~{sample}.final.bam"
	File final_bam_bai = "~{sample}.final.bam.bai"
}
runtime {
	docker: docker_image
	cpu: effective_cpu
	memory: "32 GB"
}
}

task MetaTrim3Bam {
input {
	String docker_image
	File final_bam
	File final_bam_bai
	String sample
	String threads
	Int? task_cpu
}
Int effective_cpu = select_first([task_cpu, 8])
command <<<
	set -euo pipefail
	bam trimBam "~{final_bam}" trim3.bam 3
	samtools index trim3.bam
>>>
output {
	File trim3_bam = "trim3.bam"
	File trim3_bai = "trim3.bam.bai"
}
runtime {
	docker: docker_image
	cpu: effective_cpu
	memory: "16 GB"
}
}

task MetaTypingPostTrim {
input {
	String docker_image
	File trim3_bam
	File trim3_bai
	Array[File] ref
	Array[File] dataset
	String sample
	String threads
	String pathogen
	String? ha_refname
	Int? task_cpu
}
Int effective_cpu = select_first([task_cpu, 8])
command <<<
	set -euo pipefail
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
	P="$(echo "~{pathogen}" | tr '[:lower:]' '[:upper:]' | tr '-' '_')"
	case "$P" in
	SARS_COV_2|SARS_COV2|SARSCOV2|SC2)
		P="SARSCOV2"
		;;
	esac

	if [ "$P" = "SARSCOV2" ]; then
	samtools depth -Q 20 "~{trim3_bam}" | awk '{
		t++; sd+=$3; cov+=($3>0)
		}
		END {
		printf "Genome_mean_depth: %.2f", (t>0?sd/t:0); print ""
		printf "Genome_coverage_pct: %.2f", (t>0?cov/t*100:0); print "%"
		printf "Total_positions: %d", t; print ""
		printf "Covered_positions: %d", cov; print ""
		}' > "~{sample}_coverage.txt"

	samtools mpileup -OsBa --reference "$REF_FASTA" -d 3000000 -Q 20 -q 20 "~{trim3_bam}" | \
		ivar consensus -i "~{trim3_bam}" -p "~{sample}_HA_consensus" -m 1 -t 0.6 -n N
	sed -i.bak "1s/^>.*/>~{sample}/" "~{sample}_HA_consensus.fa"
	rm -f "~{sample}_HA_consensus.fa.bak"

	nextclade run "~{sample}_HA_consensus.fa" \
		"${NC_ARGS[@]}" \
		--output-json "~{sample}_nextclade.json" \
		--output-tsv "~{sample}_nextclade.tsv" \
		--jobs ~{threads}

	TSV="~{sample}_nextclade.tsv"
	GCOV="~{sample}_coverage.txt"
	SEQ_NAME=$(awk -F"\t" 'NR==2 {print $2}' "$TSV")
	CLADE=$(awk -F"\t" 'NR==2 {print $4}' "$TSV")
	LINEAGE=$(awk -F"\t" 'NR==2 {print $7}' "$TSV")
	PANGO=$(awk -F"\t" 'NR==2 {print $8}' "$TSV")
	QC_STATUS=$(awk -F"\t" 'NR==2 {print $10}' "$TSV")
	TOTAL_MISSING=$(awk -F"\t" 'NR==2 {print $15}' "$TSV")
	GENOME_DEPTH=$(grep "Genome_mean_depth" "$GCOV" | awk '{print $2}')
	GENOME_COVERAGE=$(grep "Genome_coverage_pct" "$GCOV" | awk '{gsub(/%/,""); print $2}')
	if [ -n "$TOTAL_MISSING" ] && [ "$TOTAL_MISSING" -eq "$TOTAL_MISSING" ] 2>/dev/null; then
		COVERAGE=$(awk -v m="$TOTAL_MISSING" 'BEGIN { printf "%.2f", (29903 - m) / 29903 * 100 }')
	else
		COVERAGE="${GENOME_COVERAGE}%"
	fi
	FAILED=false
	if [ -z "$SEQ_NAME" ] || [ "$SEQ_NAME" = "" ]; then FAILED=true
	elif [ "$CLADE" = "" ] || [ "$CLADE" = "NA" ]; then FAILED=true
	elif [ "$QC_STATUS" = "" ]; then FAILED=true
	elif [ -n "$TOTAL_MISSING" ] && [ "$TOTAL_MISSING" -gt 10000 ]; then FAILED=true
	fi
	echo "sequence_name,clade,lineage,pango,quality,coverage,depth" > "~{sample}_result.csv"
	if [ "$FAILED" = true ]; then
		echo "${SEQ_NAME},Fail" >> "~{sample}_result.csv"
	else
		echo "${SEQ_NAME},${CLADE},${LINEAGE},${PANGO},${QC_STATUS},${COVERAGE},${GENOME_DEPTH}" >> "~{sample}_result.csv"
	fi
	else
	HA_REF="~{if defined(ha_refname) then ha_refname else ""}"
	test -n "$HA_REF" || { echo "ERROR: influenza typing requires HA_REFNAME" >&2; exit 1; }

	samtools view -b "~{trim3_bam}" "$HA_REF" > HA.bam
	samtools depth -Q 20 HA.bam | awk '{
		t++; sd+=$3; cov+=($3>0)
		}
		END {
		printf "HA_mean_depth: %.2f", (t>0?sd/t:0); print ""
		printf "HA_coverage_pct: %.2f", (t>0?cov/t*100:0); print "%"
		}' > "~{sample}_HA_coverage.txt"

	samtools mpileup -OsBa --reference "$REF_FASTA" -d 3000000 -Q 20 -q 20 HA.bam | \
		ivar consensus -i HA.bam -p "~{sample}_HA_consensus" -m 1 -t 0.6 -n N
	sed -i.bak "1s/^>.*/>~{sample}/" "~{sample}_HA_consensus.fa"
	rm -f "~{sample}_HA_consensus.fa.bak"

	nextclade run "~{sample}_HA_consensus.fa" \
		"${NC_ARGS[@]}" \
		--output-json "~{sample}_nextclade.json" \
		--output-tsv "~{sample}_nextclade.tsv" \
		--jobs ~{threads}

	TSV="~{sample}_nextclade.tsv"
	COV="~{sample}_HA_coverage.txt"
	HA_DEPTH=$(grep "HA_mean_depth" "$COV" | awk '{print $2}')
	PP="~{pathogen}"
	if [ "$PP" = "H3N2" ] || [ "$PP" = "h3n2" ]; then
		SEQ_NAME=$(awk -F"\t" 'NR==2 {print $2}' "$TSV")
		CLADE=$(awk -F"\t" 'NR==2 {print $3}' "$TSV")
		SUBCLADE=$(awk -F"\t" 'NR==2 {print $6}' "$TSV")
		LEGACY_CLADE=$(awk -F"\t" 'NR==2 {print $7}' "$TSV")
		QC_STATUS=$(awk -F"\t" 'NR==2 {print $11}' "$TSV")
		TOTAL_MISSING=$(awk -F"\t" 'NR==2 {print $16}' "$TSV")
		if [ -n "$TOTAL_MISSING" ] && [ "$TOTAL_MISSING" -eq "$TOTAL_MISSING" ] 2>/dev/null; then
		COVERAGE=$(awk -v m="$TOTAL_MISSING" 'BEGIN { printf "%.2f", (1718 - m) / 1718 * 100 }')
		else
		COVERAGE="N/A"
		fi
		FAILED=false
		if [ -z "$SEQ_NAME" ] || [ "$SEQ_NAME" = "" ]; then FAILED=true
		elif [ "$CLADE" = "unassigned" ] || [ "$CLADE" = "" ]; then FAILED=true
		elif [ -n "$TOTAL_MISSING" ] && [ "$TOTAL_MISSING" -gt 1100 ]; then FAILED=true
		fi
	else
		SEQ_NAME=$(awk -F"\t" 'NR==2 {print $2}' "$TSV")
		CLADE=$(awk -F"\t" 'NR==2 {print $3}' "$TSV")
		SUBCLADE=$(awk -F"\t" 'NR==2 {print $5}' "$TSV")
		LEGACY_CLADE=$(awk -F"\t" 'NR==2 {print $7}' "$TSV")
		QC_STATUS=$(awk -F"\t" 'NR==2 {print $10}' "$TSV")
		TOTAL_MISSING=$(awk -F"\t" 'NR==2 {print $15}' "$TSV")
		if [ -n "$TOTAL_MISSING" ] && [ "$TOTAL_MISSING" -eq "$TOTAL_MISSING" ] 2>/dev/null; then
		COVERAGE=$(awk -v m="$TOTAL_MISSING" 'BEGIN { printf "%.2f", (1752 - m) / 1752 * 100 }')
		else
		COVERAGE="N/A"
		fi
		FAILED=false
		if [ -z "$SEQ_NAME" ] || [ "$SEQ_NAME" = "" ]; then FAILED=true
		elif [ "$LEGACY_CLADE" = "unassigned" ] || [ "$LEGACY_CLADE" = "" ]; then FAILED=true
		elif [ -n "$TOTAL_MISSING" ] && [ "$TOTAL_MISSING" -gt 1100 ]; then FAILED=true
		fi
	fi
	echo "sequence_name,clade,subclade,legacy-clade,quality,coverage,depth" > "~{sample}_result.csv"
	if [ "$FAILED" = true ]; then
		echo "${SEQ_NAME},Fail" >> "~{sample}_result.csv"
	else
		echo "${SEQ_NAME},${CLADE},${SUBCLADE},${LEGACY_CLADE},${QC_STATUS},${COVERAGE},${HA_DEPTH}" >> "~{sample}_result.csv"
	fi
	fi
>>>
output {
	File result_csv = "~{sample}_result.csv"
	File nextclade_tsv = "~{sample}_nextclade.tsv"
	File nextclade_json = "~{sample}_nextclade.json"
	File consensus_fa = "~{sample}_HA_consensus.fa"
}
runtime {
	docker: docker_image
	cpu: effective_cpu
	memory: "32 GB"
}
}
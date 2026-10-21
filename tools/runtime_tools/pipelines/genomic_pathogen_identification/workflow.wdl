version 1.0

workflow MashIdentify {
  input {
    File query_fasta
    String sample_id = ""

    File mash_db_bacteria
    File mash_db_fungi
    File mash_db_parasite
    File mash_db_virus

    File virus_annotation
    File pathogen_annotation

    Int threads = 16

    Int sketch_k16 = 16
    Int sketch_s_k16 = 5000
    Int sketch_k21 = 21
    Int sketch_s_k21_5k = 5000
    Int sketch_s_k21_10k = 10000

    Float threshold_max_dist = 0.05
    Float threshold_max_pvalue = 0.0000000001
    Int threshold_min_shared = 200
    Float threshold_near_best_delta = 0.005
    Float threshold_near_best_ratio = 1.1

    String docker_image = "cncb/mash-identify:v1.0"
    Int cpu = 16
    Int memory_gb = 32
    Int disk_gb = 100
  }

  String sample = if (sample_id != "") then sample_id else sub(basename(query_fasta), "\\.[^.]*$", "")

  call run_mash_identify {
    input:
      query_fasta = query_fasta,
      sample = sample,
      mash_db_bacteria = mash_db_bacteria,
      mash_db_fungi = mash_db_fungi,
      mash_db_parasite = mash_db_parasite,
      mash_db_virus = mash_db_virus,
      virus_annotation = virus_annotation,
      pathogen_annotation = pathogen_annotation,
      threads = threads,
      sketch_k16 = sketch_k16,
      sketch_s_k16 = sketch_s_k16,
      sketch_k21 = sketch_k21,
      sketch_s_k21_5k = sketch_s_k21_5k,
      sketch_s_k21_10k = sketch_s_k21_10k,
      threshold_max_dist = threshold_max_dist,
      threshold_max_pvalue = threshold_max_pvalue,
      threshold_min_shared = threshold_min_shared,
      threshold_near_best_delta = threshold_near_best_delta,
      threshold_near_best_ratio = threshold_near_best_ratio,
      docker_image = docker_image,
      cpu = cpu,
      memory_gb = memory_gb,
      disk_gb = disk_gb
  }

  output {
    File summary_tsv = run_mash_identify.summary_tsv
    File per_contig_call_tsv = run_mash_identify.per_contig_call_tsv
    File annotated_hits_tsv = run_mash_identify.annotated_hits_tsv
    Array[File] mash_dist_tsv = run_mash_identify.mash_dist_tsv
  }
}

task run_mash_identify {
  input {
    File query_fasta
    String sample

    File mash_db_bacteria
    File mash_db_fungi
    File mash_db_parasite
    File mash_db_virus

    File virus_annotation
    File pathogen_annotation

    Int threads
    Int sketch_k16
    Int sketch_s_k16
    Int sketch_k21
    Int sketch_s_k21_5k
    Int sketch_s_k21_10k
    Float threshold_max_dist
    Float threshold_max_pvalue
    Int threshold_min_shared
    Float threshold_near_best_delta
    Float threshold_near_best_ratio

    String docker_image
    Int cpu
    Int memory_gb
    Int disk_gb
  }

  String summary_out = "postprocess/" + sample + ".summary.tsv"
  String per_contig_out = "postprocess/" + sample + ".per_contig_call.tsv"
  String hits_out = "postprocess/" + sample + ".annotated_hits.tsv"

  command <<<
    set -euo pipefail

    SAMPLE="~{sample}"
    mkdir -p sketches postprocess

    ln -sf ~{query_fasta} query.fa
    ln -sf ~{mash_db_bacteria} db_bacteria.msh
    ln -sf ~{mash_db_fungi} db_fungi.msh
    ln -sf ~{mash_db_parasite} db_parasite.msh
    ln -sf ~{mash_db_virus} db_virus.msh

    mash sketch -p ~{threads} -i -k ~{sketch_k16} -s ~{sketch_s_k16} \
      -o "sketches/${SAMPLE}_k16_s5k" query.fa
    mash sketch -p ~{threads} -i -k ~{sketch_k21} -s ~{sketch_s_k21_5k} \
      -o "sketches/${SAMPLE}_k21_s5k" query.fa
    mash sketch -p ~{threads} -i -k ~{sketch_k21} -s ~{sketch_s_k21_10k} \
      -o "sketches/${SAMPLE}_k21_s10k" query.fa

    mash dist -p ~{threads} db_bacteria.msh \
      "sketches/${SAMPLE}_k21_s5k.msh" > "bacteria_${SAMPLE}.mash.tsv"
    mash dist -p ~{threads} db_fungi.msh \
      "sketches/${SAMPLE}_k21_s5k.msh" > "fungi_${SAMPLE}.mash.tsv"
    mash dist -p ~{threads} db_parasite.msh \
      "sketches/${SAMPLE}_k21_s10k.msh" > "parasite_${SAMPLE}.mash.tsv"
    mash dist -p ~{threads} db_virus.msh \
      "sketches/${SAMPLE}_k16_s5k.msh" > "virus_${SAMPLE}.mash.tsv"

    python3 /app/mash_identify.py "${SAMPLE}" \
      --mash-dir . \
      --outdir postprocess \
      --virus-anno ~{virus_annotation} \
      --pathogen-anno ~{pathogen_annotation} \
      --max-dist ~{threshold_max_dist} \
      --max-pvalue ~{threshold_max_pvalue} \
      --min-shared ~{threshold_min_shared} \
      --near-best-delta ~{threshold_near_best_delta} \
      --near-best-ratio ~{threshold_near_best_ratio}
  >>>

  output {
    File summary_tsv = summary_out
    File per_contig_call_tsv = per_contig_out
    File annotated_hits_tsv = hits_out
    Array[File] mash_dist_tsv = [
      "bacteria_" + sample + ".mash.tsv",
      "fungi_" + sample + ".mash.tsv",
      "parasite_" + sample + ".mash.tsv",
      "virus_" + sample + ".mash.tsv",
    ]
  }

  runtime {
    docker: docker_image
    cpu: cpu
    memory: memory_gb + " GB"
    disks: "local-disk " + disk_gb + " SSD"
  }
}

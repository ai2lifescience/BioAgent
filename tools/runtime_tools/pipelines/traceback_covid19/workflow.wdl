version 1.0

## 与 ISimilarSequenceServiceImpl.run 步骤对齐：concat → mafft → MSA2Sample_Mutlist →
## GenotypeDistanceCalculator → Mutlist2SNP_Sequence → FastTree
## Valkyrie 参考文件由 workflow 输入 Array[File] 传入（提交方按 d_method 解析，见 ValkyrieInputsResolver）。

workflow similar_sequence {
  input {
    File reference_fasta
    File query_fasta
    String d_method = "WM"
    Array[File] valkyrie_files
    String valkyrie_relative_path_inside_tar = "Valkyrie"
    File indel_info
    String output_name_prefix = "query"
    Int mafft_threads = 4

    String docker_image = "cncb/genome_tracing:v1.0"
  }

  String genotype_extra = if (d_method == "WM+LD") then "-LD" else if (d_method == "UM") then "-MO" else if (d_method == "WM+CL") then "-CL" else if (d_method == "WM+CL+LD") then "-LDCL" else ""

  call combine_fasta {
    input:
      reference_fasta = reference_fasta,
      query_fasta = query_fasta,
      docker_image = docker_image
  }

  call run_mafft {
    input:
      combined_fa = combine_fasta.combined_fa,
      output_name_prefix = output_name_prefix,
      mafft_threads = mafft_threads,
      docker_image = docker_image
  }

  call run_msa2_mutlist {
    input:
      mafft_result = run_mafft.mafft_result,
      output_name_prefix = output_name_prefix,
      docker_image = docker_image
  }

  call run_genotype_distance {
    input:
      mutation_file = run_msa2_mutlist.mutation_file,
      valkyrie_files = valkyrie_files,
      valkyrie_relative_path_inside_tar = valkyrie_relative_path_inside_tar,
      genotype_extra = genotype_extra,
      docker_image = docker_image
  }

  call run_mutlist2_snp {
    input:
      result_mutlist = run_genotype_distance.result_mutlist,
      indel_info = indel_info,
      docker_image = docker_image
  }

  call run_fasttree {
    input:
      snp_fa = run_mutlist2_snp.snp_fa,
      docker_image = docker_image
  }

  output {
    File combined_fa = combine_fasta.combined_fa
    File mafft_result = run_mafft.mafft_result
    File mutation_file = run_msa2_mutlist.mutation_file
    File result_tsv = run_genotype_distance.result_tsv
    File result_mutlist = run_genotype_distance.result_mutlist
    File snp_fa = run_mutlist2_snp.snp_fa
    File tree_file = run_fasttree.tree_file
  }
}

task combine_fasta {
  input {
    File reference_fasta
    File query_fasta
    String docker_image
  }
  command <<<
    set -euo pipefail
    cat ~{reference_fasta} ~{query_fasta} > combined.fa
  >>>
  output {
    File combined_fa = "combined.fa"
  }
  runtime {
    docker: docker_image
    memory: "16 GB"
    cpu: 8
  }
}

task run_mafft {
  input {
    File combined_fa
    String output_name_prefix
    Int mafft_threads
    String docker_image
  }
  String mafft_out = output_name_prefix + ".mafft_result"
  command <<<
    set -euo pipefail
    ln -sf ~{combined_fa} combined.fa
    mafft --auto --quiet --thread ~{mafft_threads} combined.fa > ~{mafft_out}
  >>>
  output {
    File mafft_result = mafft_out
  }
  runtime {
    docker: docker_image
    memory: "8 GB"
    cpu: mafft_threads
  }
}

task run_msa2_mutlist {
  input {
    File mafft_result
    String output_name_prefix
    String docker_image
  }
  String mafft_basename = basename(mafft_result)
  String mutation_out = output_name_prefix + ".mutation_result"
  command <<<
    set -euo pipefail
    ln -sf ~{mafft_result} ~{mafft_basename}
    MSA2Sample_Mutlist.out ~{mafft_basename} ~{mutation_out}
  >>>
  output {
    File mutation_file = mutation_out
  }
  runtime {
    docker: docker_image
    memory: "4 GB"
    cpu: 2
  }
}

task run_genotype_distance {
  input {
    File mutation_file
    Array[File] valkyrie_files
    String valkyrie_relative_path_inside_tar
    String genotype_extra
    String docker_image
  }
  command <<<
    set -euo pipefail
    VALDIR="$(pwd)/~{valkyrie_relative_path_inside_tar}"
    mkdir -p "$VALDIR"
    for src in ~{sep=' ' valkyrie_files}; do
      ln -sf "$src" "$VALDIR/$(basename "$src")"
    done
    MUT="$(tr -d '\r' < ~{mutation_file})"
    MUT="${MUT#"${MUT%%[![:space:]]*}"}"
    MUT="${MUT%"${MUT##*[![:space:]]}"}"
    if [ -z "$MUT" ]; then
      echo "mutation 文件为空" >&2
      exit 3
    fi
    GenotypeDistanceCalculator.out "$VALDIR" "$MUT" ResultGenotypeRank.tsv ~{genotype_extra}
  >>>
  output {
    File result_tsv = "ResultGenotypeRank.tsv"
    File result_mutlist = "ResultGenotypeRank.tsv.mutlist"
  }
  runtime {
    docker: docker_image
    memory: "16 GB"
    cpu: 4
  }
}

task run_mutlist2_snp {
  input {
    File result_mutlist
    File indel_info
    String docker_image
  }
  command <<<
    set -euo pipefail
    ln -sf ~{result_mutlist} ResultGenotypeRank.tsv.mutlist
    Mutlist2SNP_Sequence.out ResultGenotypeRank.tsv.mutlist ~{indel_info}
  >>>
  output {
    File snp_fa = "ResultGenotypeRank.tsv.mutlist.snp.fa"
  }
  runtime {
    docker: docker_image
    memory: "8 GB"
    cpu: 2
  }
}

task run_fasttree {
  input {
    File snp_fa
    String docker_image
  }
  command <<<
    set -euo pipefail
    ln -sf ~{snp_fa} ResultGenotypeRank.tsv.mutlist.snp.fa
    FastTree -gtr -nt -quiet ResultGenotypeRank.tsv.mutlist.snp.fa > tree_file
  >>>
  output {
    File tree_file = "tree_file"
  }
  runtime {
    docker: docker_image
    memory: "8 GB"
    cpu: 2
  }
}

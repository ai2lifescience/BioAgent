nextflow.enable.dsl = 2


process ANALYZE_SEQUENCE {
    tag "${params.label ?: 'generic_nextflow'}"
    cpus { Math.max(1, (params.cores ?: 1) as int) }
    publishDir params.nextflow_output_dir, mode: 'copy', overwrite: true

    input:
    path sequence
    path metadata
    path runtime_config

    output:
    path 'normalized.fasta', emit: normalized_sequence
    path 'metrics.json', emit: metrics
    path 'report.md', emit: report

    script:
    """
    python3 "${projectDir}/workflow.py" \\
      --config "${runtime_config}" \\
      --input "${sequence}" \\
      --metadata "${metadata}"
    """
}


workflow {
    if (!params.input_path) {
        error 'Missing required parameter: input_path'
    }
    if (!params.metadata_path) {
        error 'Missing required parameter: metadata_path'
    }
    if (!params.bioagent_config_path) {
        error 'Missing BioAgent runtime parameter: bioagent_config_path'
    }
    if (!params.nextflow_output_dir) {
        error 'Missing BioAgent runtime parameter: nextflow_output_dir'
    }

    sequence_ch = Channel.value(file(params.input_path, checkIfExists: true))
    metadata_ch = Channel.value(file(params.metadata_path, checkIfExists: true))
    runtime_config_ch = Channel.value(file(params.bioagent_config_path, checkIfExists: true))

    ANALYZE_SEQUENCE(sequence_ch, metadata_ch, runtime_config_ch)
}

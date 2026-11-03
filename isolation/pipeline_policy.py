"""Workflow execution policy, separate from engine compatibility."""
from auth import ExecutionUnavailable


# These workflows remain outside the supported safety scope. This is not an
# engine-adapter registry: other installed plugins are discovered from manifests.
RESTRICTED_WORKFLOWS = frozenset({
    'antimicrobial_resistance_detection',
    'bacterial_genome_mutation_analysis',
    'bacterial_read_variant_analysis',
    'bacterial_virulence_factor_detection',
    'pathogen_variant_risk_assessment',
    'viral_genome_mutation_analysis',
    'viral_molecular_typing',
})


def require_workflow(name):
    if name in RESTRICTED_WORKFLOWS:
        raise ExecutionUnavailable('Execution is disabled by workflow safety policy; this is not an engine compatibility error.')

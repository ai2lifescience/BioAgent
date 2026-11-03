"""Public readiness metadata derived from the real execution routes."""
import os
import shutil

from .registry import build_all_tools


def describe(pipelines):
    from isolation import isolated_execution
    from isolation.policy import OFFLINE_TOOLS, SERVICE_TOOLS
    from isolation.network import NETWORK_TOOLS
    from isolation.embeddings import TOOLS as EMBEDDING_TOOLS
    from tools.infrastructure.pipeline_engine import broker, contracts
    from auth import ExecutionUnavailable
    isolated = isolated_execution()
    worker_ready = True
    if isolated:
        from isolation.supervisor import ensure_available
        from auth import ExecutionUnavailable
        try: ensure_available()
        except ExecutionUnavailable: worker_ready = False
    worker_reason = 'Build the current worker image and make Docker available to the server.'
    tools = {}
    for tool in build_all_tools('unused'):
        name = tool.name
        route = ('container' if name in OFFLINE_TOOLS else 'provider_broker' if name in NETWORK_TOOLS
                 else 'embedding_broker' if name in EMBEDDING_TOOLS else 'knowledge_service' if name in SERVICE_TOOLS
                 else 'pipeline_broker' if name == 'pipeline_shell' else 'agent_or_service') if isolated else 'local'
        needs_key = name in EMBEDDING_TOOLS | {'knowledge_ingest', 'knowledge_retrieve', 'report_review', 'report_synthesize', 'research_specialist'}
        ready = not needs_key or bool(os.getenv('OPENROUTER_API_KEY', '').strip())
        tools[name] = {'status': 'available' if ready else 'needs_configuration', 'execution': route,
                       'reason': '' if ready else 'Configure the server model/embedding credentials.'}
        if isolated and not worker_ready:
            tools[name].update(status='needs_configuration', reason=worker_reason)
    workflows = {}
    for item in pipelines:
        name, engine = item['name'], item.get('engine')
        execution = engine
        status, reason = 'available', ''
        if isolated:
            try:
                execution = contracts.backend(name)
            except ExecutionUnavailable as exc:
                status, reason = 'unsupported', str(exc)
            except (ValueError, OSError):
                status, reason = 'unsupported', 'Pipeline manifest is missing, invalid, or declares an unsupported engine.'
            if status == 'available' and execution == 'cromwell':
                try: broker._configured()
                except Exception:
                    status, reason = 'needs_configuration', 'Configure Cromwell and input/output storage on the server.'
            if status == 'available' and not worker_ready:
                status, reason = 'needs_configuration', worker_reason
        elif engine == 'nextflow' and not shutil.which('nextflow'):
            status, reason = 'needs_configuration', 'Install Nextflow and Java on the server.'
        workflows[name] = {'status': status, 'reason': reason, 'execution': execution}
    dependencies = {
        'NCBI genome map': ['ncbi_retrieval', 'genome_read_features', 'genome_render_map'],
        'PDB structure viewer': ['pdb_download', 'structure_inspect'],
        'Knowledge ingest and retrieve': ['knowledge_ingest', 'knowledge_status', 'knowledge_retrieve'],
        'Plot synthetic data': ['python_execute'],
        'Research and report': ['pubmed_search', 'web_fetch', 'evidence_retrieve', 'report_review', 'report_synthesize', 'report_write'],
    }
    starters = {}
    for label, names in dependencies.items():
        unavailable = [tools.get(name, {'status': 'unsupported', 'reason': name + ' is not registered.'}) for name in names
                       if tools.get(name, {}).get('status') != 'available']
        starters[label] = unavailable[0] if unavailable else {'status': 'available', 'reason': ''}
    starters['Metagenomic read quality control'] = workflows.get('metagenomic_read_quality_control', {'status': 'unsupported', 'reason': 'Workflow is not installed.'})
    return {'tools': tools, 'pipelines': workflows, 'quick_starts': starters}

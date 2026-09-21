"""Species report tool workflow."""
from __future__ import annotations
from tools.function_tools.species_report.literature.core import collect_pubmed_records as _action_pubmed_collect
from tools.function_tools.species_report.web.core import collect_trusted_web_records as _action_trusted_web_collect
from tools.function_tools.species_report.rag.chunk import rag_chunk_tool as _action_rag_chunk
from tools.function_tools.species_report.rag.store import rag_store_tool as _action_rag_store
from tools.function_tools.species_report.rag.retrieve import rag_retrieve_tool as _action_rag_retrieve
from tools.function_tools.species_report.rag.cite import rag_citations_tool as _action_rag_citations
from tools.function_tools.species_report.reporting.opinions import collect_species_model_opinions as _action_species_model_opinions
from tools.function_tools.species_report.reporting.synthesis import synthesize_species_markdown_report as _action_species_report_synthesis
from tools.function_tools.species_report.writer import write_markdown_report as _action_markdown_report_writer
from typing import Any, Callable
from tools.infrastructure.tooling.context import WorkflowContext, ensure_workflow_context
from tools.infrastructure.workspace import session_output_dir, workspace_output_dir
from tools.function_tools.species_report.research import build_research_question, build_source_query, collection_name_for, normalize_text, source_summary
DEFAULT_MAX_PUBMED = 6
DEFAULT_MAX_WEB_PAGES = 6
DEFAULT_TOP_K = 6

def _emit(log_fn: Callable[[str], None] | None, message: str) -> None:
    if log_fn:
        log_fn(f'[species_report] {message}')

def species_report(species_name: str | None=None, species: str | None=None, question: str | None=None, concerns: list[str] | None=None, max_pubmed: int=DEFAULT_MAX_PUBMED, max_web_pages: int=DEFAULT_MAX_WEB_PAGES, top_k: int=DEFAULT_TOP_K, collection_name: str | None=None, chroma_path: str | None=None, output_dir: str | None=None, context: WorkflowContext | None=None, log_fn: Callable[[str], None] | None=None) -> dict[str, Any]:
    context = ensure_workflow_context(context, 'species_report')
    chroma_path = str(session_output_dir(context, chroma_path, 'runs', 'chroma'))
    output_dir = str(workspace_output_dir(context, output_dir, 'reports'))
    resolved_species = normalize_text(species_name or species or '')
    if not resolved_species:
        raise ValueError('species_name or species is required.')
    if max_pubmed < 1:
        raise ValueError('max_pubmed must be at least 1.')
    if max_web_pages < 0:
        raise ValueError('max_web_pages cannot be negative.')
    if top_k < 1:
        raise ValueError('top_k must be at least 1.')
    research_question = build_research_question(species_name=resolved_species, question=question, concerns=concerns)
    source_query = build_source_query(question=question, concerns=concerns)
    _emit(log_fn, f'Collecting PubMed records for {resolved_species}.')
    pubmed_result = context.call('pubmed_collect', _action_pubmed_collect, {'species_name': resolved_species, 'question': source_query, 'max_records': max_pubmed})['result']
    _emit(log_fn, f"Collected {pubmed_result.get('record_count', 0)} PubMed record(s).")
    _emit(log_fn, f'Collecting up to {max_web_pages} trusted web page(s).')
    web_result = context.call('trusted_web_collect', _action_trusted_web_collect, {'species_name': resolved_species, 'question': source_query, 'max_pages': max_web_pages})['result']
    _emit(log_fn, f"Collected {web_result.get('record_count', 0)} trusted web page(s).")
    records = [*pubmed_result.get('records', []), *web_result.get('records', [])]
    if not records:
        raise RuntimeError(f"No trusted source records were found for '{resolved_species}'. Try a broader species name or concern.")
    _emit(log_fn, f'Chunking {len(records)} source record(s).')
    chunk_result = context.call('rag_chunk', _action_rag_chunk, {'records': records})['result']
    chunks = chunk_result.get('chunks', [])
    if not chunks:
        raise RuntimeError(f"Trusted records for '{resolved_species}' had no usable text.")
    _emit(log_fn, f'Created {len(chunks)} text chunk(s).')
    resolved_collection_name = collection_name_for(resolved_species, collection_name)
    _emit(log_fn, f'Embedding chunks and storing them in Chroma collection {resolved_collection_name}.')
    context.call('rag_store', _action_rag_store, {'records': chunks, 'collection_name': resolved_collection_name, 'chroma_path': chroma_path})
    _emit(log_fn, 'Retrieving ranked RAG evidence chunks.')
    retrieve_result = context.call('rag_retrieve', _action_rag_retrieve, {'question': research_question, 'collection_name': resolved_collection_name, 'chroma_path': chroma_path, 'top_k': min(top_k, len(chunks))})['result']
    _emit(log_fn, f"Retrieved {retrieve_result.get('chunk_count', 0)} ranked chunk(s).")
    citation_result = context.call('rag_citations', _action_rag_citations, {'chunks': retrieve_result.get('chunks', [])})['result']
    retrieval_context = citation_result.get('context') or retrieve_result.get('context', '')
    _emit(log_fn, 'Requesting parallel direct LLM opinions.')
    model_opinion_result = context.call('species_model_opinions', _action_species_model_opinions, {'species_name': resolved_species, 'question': research_question, 'agent_context': context.user_context.get('_agent_context')})['result']
    sources = source_summary(records)
    _emit(log_fn, 'Synthesizing final Markdown report.')
    synthesis_result = context.call('species_report_synthesis', _action_species_report_synthesis, {'species_name': resolved_species, 'question': research_question, 'retrieval_context': retrieval_context, 'model_answers': model_opinion_result['model_answers'], 'sources': sources, 'agent_context': context.user_context.get('_agent_context')})['result']
    writer_result = context.call('markdown_report_writer', _action_markdown_report_writer, {'markdown': synthesis_result['markdown'], 'entity_name': resolved_species, 'output_dir': output_dir, 'suffix': 'knowledge'})['result']
    _emit(log_fn, f"Report saved to {writer_result['report_path']}.")
    return {'workflow': 'species_report', 'species': resolved_species, 'species_name': resolved_species, 'question': research_question, 'answer': synthesis_result['markdown'], 'report_path': writer_result['report_path'], 'collection_name': resolved_collection_name, 'chroma_path': chroma_path, 'source_count': len(records), 'chunk_count': len(chunks), 'sources': sources, 'retrieval_context': retrieval_context, 'retrieved_chunks': retrieve_result.get('chunks', []), 'citations': citation_result.get('citations', []), 'model_answers': model_opinion_result['model_answers']}

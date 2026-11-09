import type { AppConfig, Capability, Pipeline } from '../../types';

export const fallbackPipelines: Pipeline[] = [
  ['metagenomic_de_novo_assembly', 'Metagenomic de novo assembly'],
  ['metagenomic_pathogen_identification', 'Metagenomic pathogen identification'],
  ['metagenomic_read_quality_control', 'Metagenomic read quality control'],
  ['template_bio', 'DNA analysis template'], ['template_nextflow', 'Nextflow pipeline template'],
  ['template_shell', 'Shell metadata assignment template'], ['template_snakemake', 'Snakemake pipeline template'],
  ['template_wdl', 'WDL pipeline template'],
].map(([name, display_name]) => ({ name, display_name }));

const quickStarts = [
  ['NCBI genome map', 'Use ncbi_retrieval to download NCBI accession NC_001422.1 as a FASTA file.\nThen use the downloaded FASTA to find ORFs and render an interactive genome map.\nReturn the downloaded path, map path, and reference path.'],
  ['PDB structure viewer', 'Download PDB structure 1A3N as mmCIF, inspect its chains and ligands, and show the interactive 3D structure viewer.'],
  ['Metagenomic read quality control', 'Run the Metagenomic read quality control pipeline (pipeline_name: metagenomic_read_quality_control). Use any parameter values from my request and ask me for missing required values before executing.'],
  ['Knowledge ingest and retrieve', [
    'Build and query a durable knowledge collection using only `knowledge_ingest`, `knowledge_status`, and `knowledge_retrieve`.',
    '### 1. Ingest',
    'Create a new session-owned collection with these parameters:\n- `seed_urls`: ["https://rest.uniprot.org/uniprotkb/P0A7V8.txt"]\n- `allowed_domains`: ["rest.uniprot.org"]\n- `max_pages`: 1\n- `max_depth`: 0',
    'Poll `knowledge_status` until terminal. Report `job_id`, `collection_id`, status, fetched/indexed/chunks, skipped URLs, and errors. Proceed only if status is `succeeded`, indexed > 0, and chunks > 0; otherwise explain the reported failure or empty result and stop.',
    '### 2. Retrieve',
    'Use the returned `collection_id` in this same session. Call `knowledge_retrieve` twice with `top_k=8` and these exact question values:\n1. `FUNCTION`\n2. `InterPro`',
    'This collection contains only P0A7V8, so do not add other words to either query. Do not ingest again or use web/database tools.',
    '### 3. Present the evidence',
    '- Summarize the protein functions.\n- Show a two-column table of InterPro IDs and entry names exactly as recorded.\n- Put identifiers and entry names in inline code to preserve underscores; do not infer family/domain/site classifications.\n- Include source URLs, supporting chunk IDs, brief excerpts, and every `evidence_path`.\n- Explicitly identify anything unsupported by the retrieved evidence.',
  ].join('\n\n')],
  ['Plot synthetic data', 'Create and display a polished plot using only synthetic data generated inside the code.\nDo not depend on uploaded files, workspace data, databases, APIs, or internet access.\nGenerate the sample data programmatically, execute the code, save the plot as a PNG in the workspace, verify that it exists, show it directly in the chat, and return the exact path with a brief explanation.'],
  ['Research and report', [
    'Research the reliability of AI agents for scientific research, focusing on citation accuracy, reproducibility, and human oversight. Complete all steps below in this turn.',
    '### 1. Search and collect',
    'Use pubmed_search and web_search to find 6–8 relevant, distinct sources. Prefer primary research and official institutional publications. Record the search date and queries.',
    'Fetch PubMed records/abstracts and relevant web pages using the available tools, including web_fetch. Preserve source identifiers, URLs, publication dates, and actual returned workspace evidence paths.',
    'Distinguish abstracts from full-text sources. Report inaccessible sources and insufficient evidence. Distinguish evaluations of AI agents from studies of standalone language models.',
    '### 2. Retrieve and review',
    'Use evidence_retrieve with the actual returned evidence paths to select supporting excerpts.',
    'Before synthesis, use report_review to assess each source’s:\n- Study type and methods\n- Evaluation setting and sample\n- Main results\n- Uncertainty and limitations',
    'Compare conflicting findings and distinguish empirical evidence from opinion or guidance. Do not invent citations, paths, or numerical results.',
    '### 3. Synthesize and save',
    'Use report_synthesize, then report_write, to save a cited Markdown report containing:',
    '- Title and executive summary\n- Research question and search methods\n- Main findings with citations\n- Evidence comparison table: source, study type, setting/sample, results, and limitations\n- Conflicting evidence and uncertainty\n- Overall limitations and evidence gaps\n- Conclusion\n- References with PMID, DOI, or URL where available\n- Source-to-evidence mapping with exact workspace paths',
    '### 4. Read back and display',
    'After saving, use file_inspection to read the actual report_path returned by report_write.',
    'Display the saved report’s substantive contents directly in this chat, including its title, section headings, main findings with citations, evidence comparison table, uncertainty, limitations, evidence gaps, conclusion, references, and source evidence paths.',
    'Base this display on the saved file. Do not run new searches or regenerate the report after saving. If reading is truncated, read the remaining content when possible; otherwise explicitly disclose what could not be read. If verification fails, report the failure rather than claiming the file was verified.',
    'Use readable Markdown headings, lists, and tables. Show the report once, without raw tool JSON or duplicated summaries.',
    'End with:\n- Exact saved report_path\n- Number of distinct sources reviewed\n- Exact evidence artifact paths',
    'Do not return only a file path or download link.',
  ].join('\n\n')],
];
export function QuickStarts({ pipelines, isolated, capabilities, onChoose }: { pipelines: Pipeline[]; isolated?: boolean; capabilities?: AppConfig['capabilities']; onChoose: (text: string) => void }) {
  const badge = (state?: Capability) => state && <small className={`capability-status capability-${state.status}`}>{state.status === 'available' ? 'Available' : state.reason}</small>;
  const pipelinePrompt = (entry: Pipeline) => {
    const label = entry.display_name || entry.name;
    return `Run the ${label} pipeline (pipeline_name: ${entry.name}). Use any parameter values from my request and ask me for missing required values before executing.`;
  };
  return <div className="empty-state"><div className="empty-intro"><span className="empty-kicker">A focused workspace for biology</span><h1>What are you working on?</h1><p>Ask a question, upload data, or run a reproducible pipeline. Results and files stay together in this chat.</p></div><div className="onboarding-card"><div className="section-heading"><div><span className="eyebrow">Quick starts</span><span className="section-note">Choose a starting point</span></div><span className="section-count">{pipelines.length} pipelines</span></div><div className="quick-grid">{quickStarts.map(([label, prompt]) => <button key={label} title={capabilities?.quick_starts[label]?.reason} onClick={() => onChoose(prompt)}>{label}{badge(capabilities?.quick_starts[label])}</button>)}</div>{isolated && <p className="section-note">All starters and pipelines are shown. Availability reflects installed adapters and configuration; external services may still be unavailable.</p>}<details open className="pipeline-list"><summary>More pipelines <span>Explore reproducible workflows</span></summary><div className="pipeline-grid">{pipelines.map(entry => <button key={entry.name} title={capabilities?.pipelines[entry.name]?.reason} onClick={() => onChoose(pipelinePrompt(entry))}>{entry.display_name || entry.name}{badge(capabilities?.pipelines[entry.name])}</button>)}</div></details></div><div className="workflow-card"><div className="section-heading"><div><span className="eyebrow">Simple workflow</span><span className="section-note">From question to result</span></div></div><ol><li><span>1</span><div><strong>Ask</strong><small>Describe the biology task in plain language.</small></div></li><li><span>2</span><div><strong>Work</strong><small>Pipeline2Agent selects tools and inspects your files.</small></div></li><li><span>3</span><div><strong>Review</strong><small>Approve pipelines and download verified outputs.</small></div></li></ol></div></div>;
}

# Function tools

This directory is the model-facing capability layer. Each atomic capability is
one OpenAI Agents SDK `FunctionTool` exported by a category module and registered
explicitly in [`__init__.py`](__init__.py). The package exports `FUNCTION_TOOLS`;
import individual tools directly from their modules.

The package groups these narrow capabilities by stable ownership boundary:

```text
biology/   sequence_*, genome_*, structure_inspect, blast_search,
           alphafold_download, pdb_download, ncbi_retrieval, database_lookup
data_analysis/ table_profile, table_group, table_plot
sources/   pubmed_search, web_search, web_fetch
knowledge/ evidence_index, evidence_retrieve, knowledge_*
workspace/ file_inspection, document_read, workspace_search, report_write
coding/    code_inspection, code_edit, code_test
```

Capabilities compose through data flow: a tool returns a workspace-relative
artifact path and the agent may pass that path to the next tool. This is not
hidden Python dispatch.

Agents choose each step through the SDK tool loop. `report_review` and
`report_synthesize` are `Agent.as_tool()` capabilities in
`tools/agent_tools/reporting/`, because they are model-backed; the other entries are typed
FunctionTools.

Each tool module owns its SDK input schema and public `FunctionTool` wrapper.
Provider clients and parsers live in `tools/infrastructure/providers/` and
workspace adapters live in `tools/infrastructure/workspace/`; they are never
registered as model-facing tools. Generic execution and artifact handling live
in `tools/infrastructure/tool_support/`. Public tools do not call other public
tools.

Every result uses the typed `FunctionResult[T]` envelope with bounded data, evidence,
and workspace-relative artifact metadata. Host paths remain an internal
runtime detail and are projected out before results reach the model or browser.

`evidence_index` and `evidence_retrieve` are run-local operations over evidence
artifacts. The `knowledge_*` tools are the durable RAG boundary: ingestion
submits a bounded crawler job, status observes that job, and retrieval returns
an evidence artifact that `report_synthesize` can cite. Crawling, extraction,
embedding, and collection storage live privately in
`tools/infrastructure/knowledge/`; they are not public SDK tools.

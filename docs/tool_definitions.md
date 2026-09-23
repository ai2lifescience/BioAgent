# Tool definitions

This document defines the model-facing tool surfaces in Pipeline2Agent. It
complements [pipeline_definitions.md](pipeline_definitions.md), which defines
workflow manifests under tools/runtime_tools/pipelines.

The important distinction is:

| Surface | SDK object | Purpose |
| --- | --- | --- |
| Atomic function tool | FunctionTool | One bounded operation with typed JSON input and a typed result |
| Specialist | Agent.as_tool | A bounded nested agent that composes several tools |
| Pipeline runtime | ShellTool | One allowlisted agent-pipeline command for durable workflow execution |
| Hosted or remote tool | Hosted/MCP tool | Optional external capability; currently no hosted tools are registered |

Providers, crawlers, repositories, parsers, and pipeline engines are
implementation services. They are not directly exposed to the model.

## Registration flow

The root agent receives one flattened list:

~~~text
tools/function_tools/__init__.py
  -> FUNCTION_TOOLS
tools/agent_tools/registry.py
  -> specialist Agent.as_tool tools
tools/hosted_tools/__init__.py
  -> HOSTED_TOOLS
tools/infrastructure/sdk_adapters
  -> RUNTIME_TOOLS, including pipeline_shell
tools/registry.py
  -> build_all_tools(model)
harness/agent.py
  -> Pipeline2Agent(SandboxAgent, tools=build_all_tools(model))
~~~

Registration is explicit. The runtime does not scan Python files or infer tools
from filenames. Adding a module without exporting it from the registry does not
make it available to the agent.

## Atomic FunctionTools

An atomic FunctionTool should represent one clear operation that an agent can
compose with other operations. Current groups are:

| Group | Examples |
| --- | --- |
| biology | sequence statistics, ORFs, translation, genome features/maps, BLAST, structure inspection, NCBI, PDB, and AlphaFold |
| data_analysis | table profiling, grouping, and plotting |
| sources | PubMed search, web search, and web fetch |
| knowledge | durable ingestion/status/retrieval and run-local evidence indexing/retrieval |
| workspace | file inspection, document reading, workspace search, and report writing |
| coding | code inspection, code editing, and code tests |
| website | trusted page context, tables, figures, manuals, imports, highlights, navigation, and actions |

Each public function tool is defined in one category module under
tools/function_tools. The module should own:

1. its public input schema;
2. its result model;
3. its deterministic or provider-backed operation;
4. its SDK FunctionTool wrapper;
5. its public error and artifact behavior.

A public tool should not call another public model-facing tool. Shared work
belongs in tools/infrastructure services or providers. The agent composes tools
by passing actual result values and workspace-relative paths from one call to
the next.

## FunctionTool input definition

Use the shared decorator:

~~~python
from typing import Annotated

from agents import RunContextWrapper
from pydantic import Field

from harness.context import AgentRunContext
from tools.infrastructure.tool_support.decorators import bio_function_tool
from tools.infrastructure.tool_support.results import (
    FunctionContract,
    FunctionResult,
)


class SequenceResult(FunctionContract):
    length: int
    gc_fraction: float


@bio_function_tool(timeout=120)
async def sequence_stats(
    ctx: RunContextWrapper[AgentRunContext],
    sequence: Annotated[
        str,
        Field(
            min_length=1,
            max_length=1_000_000,
            description="Nucleotide sequence or workspace-relative FASTA path.",
        ),
    ],
) -> FunctionResult[SequenceResult]:
    ...
~~~

The decorator applies:

- strict SDK schema generation;
- input guardrails;
- output guardrails;
- a bounded timeout;
- the standard SDK failure handler;
- optional approval when needs_approval=True.

Use precise parameter types, Literal values, bounds, and Field descriptions.
Descriptions should explain the user intent, accepted inputs, prerequisites,
side effects, and important limits.

Avoid a vague definition such as:

~~~python
@bio_function_tool()
async def analyze(value: str):
    ...
~~~

Prefer a narrow name and explicit schema such as sequence_stats,
table_profile, or structure_inspect. Similar tools must explain how they differ.

## FunctionTool result definition

Return the common FunctionResult envelope:

~~~json
{
  "status": "ok",
  "data": {},
  "files": [],
  "evidence": [],
  "error": null
}
~~~

The envelope has these fields:

| Field | Meaning |
| --- | --- |
| status | ok, error, or blocked |
| data | Typed operation result |
| files | Workspace-relative artifact metadata |
| evidence | Sources, records, queries, and provenance |
| error | Structured error code and message when execution fails |

FunctionContract rejects undeclared fields at the public boundary. Errors should
explain what failed and what input or correction is needed. Do not return an
unbounded traceback, secret, host path, or raw provider response.

Artifacts use metadata such as:

~~~json
{
  "path": "outputs/report.md",
  "workspace_path": "outputs/report.md",
  "name": "report.md",
  "kind": "report",
  "content_type": "text/markdown",
  "size": 2048,
  "modified_at": 1730000000000000000
}
~~~

The model and browser see workspace-relative paths. The host path used by a
provider or worker remains internal to the runtime.

## Choosing a FunctionTool

The model receives the tool name, description, schema, system instructions,
conversation, previous tool results, and current workspace context. It selects
zero, one, or several tools through the SDK tool loop.

Selection should follow the narrowest useful operation:

| User intent | Tool |
| --- | --- |
| Calculate sequence measurements | sequence_stats |
| Find open reading frames | sequence_find_orfs |
| Translate a sequence | sequence_translate |
| Read an existing structure | structure_inspect |
| Download a PDB file | pdb_download |
| Search current sources | web_search or pubmed_search |
| Read a fetched page | web_fetch |
| Profile a table | table_profile |
| Create a plot | table_plot |
| Read a PDF | document_read |
| Save supplied Markdown | report_write |
| Inspect code without editing | code_inspection |

Tool names and descriptions are routing metadata, not a deterministic classifier.
When a request is ambiguous, the agent should inspect available files or ask a
focused clarification. Server-side validation remains authoritative.

## Agent-as-tool specialists

A specialist is appropriate when a task requires several dependent operations,
focused instructions, or domain-specific coordination. It is not a replacement
for an atomic operation.

Specialist modules define:

~~~python
NAME = "data_analysis_specialist"
DESCRIPTION = "Profile, summarize, group, and visualize uploaded tabular data."
INSTRUCTIONS = (
    "Start with table_profile when the schema is unknown. "
    "Use actual returned columns for later grouping and plotting."
)
TOOL_NAMES = frozenset({
    "table_profile",
    "table_group",
    "table_plot",
    "file_inspection",
    "workspace_search",
})
~~~

The shared factory validates that every named tool exists, constructs a nested
SDK Agent with the selected tools and guardrails, and exposes it through
Agent.as_tool. The root agent keeps control of the user-facing conversation.

Current specialists are:

| Specialist | Tool composition |
| --- | --- |
| research_specialist | Sources, database lookup, evidence, knowledge, report review/synthesis, report writing |
| pipeline_specialist | pipeline_shell |
| document_specialist | Workspace search, document reading, file inspection |
| data_analysis_specialist | Table tools, file inspection, workspace search |
| coding_specialist | Code inspection, editing, and tests |
| website_guide_specialist | Website tools plus table and workspace inspection |
| report_review | Evidence-bound nested review agent |
| report_synthesize | Evidence-bound nested synthesis agent |

Use a specialist when the user asks for a coordinated outcome such as
“research, review the evidence, synthesize, and save a cited report.” Use direct
FunctionTools for one clear operation such as “calculate GC content.”

Specialists receive a typed task containing the goal, known inputs, constraints,
and expected output. They do not automatically receive the full conversation.
The shared result extractor returns a summary and workspace-relative paths.

## Runtime ShellTool: pipeline_shell

pipeline_shell is the only current runtime ShellTool. It does not expose
arbitrary shell commands. Its input is exactly one allowlisted
agent-pipeline command.

~~~text
agent-pipeline catalog
agent-pipeline files
agent-pipeline example --pipeline NAME
agent-pipeline plan --pipeline NAME --input SLOT=WORKSPACE_PATH
agent-pipeline run --plan-id PLAN_ID
agent-pipeline jobs
agent-pipeline status --job-id JOB_ID
agent-pipeline wait --job-id JOB_ID --seconds 5
agent-pipeline results --job-id JOB_ID
agent-pipeline cancel --job-id JOB_ID
~~~

The agent should use catalog, files, and plan before run. Pipeline manifests and
their metadata are documented in [pipeline_definitions.md](pipeline_definitions.md).

Pipeline run and cancellation use SDK approval. Catalog, files, example
staging, planning, status, bounded wait, and results inspection do not. The
pipeline service validates input confinement, required slots, accepted suffixes,
parameters, resource limits, definition hashes, and declared outputs.

## Website tools

Website tools are ordinary SDK FunctionTools backed by the authenticated
harness/website.py bridge. They do not create a second agent runtime.

| Tool | Purpose |
| --- | --- |
| website_context | Read the current structured page snapshot |
| website_read_table | Read one bounded page of a registered table |
| website_read_figure | Read structured chart values and semantics |
| website_search_manual | Search the host manual |
| website_read_manual | Read one versioned manual section |
| website_import_data | Export host data into inputs/ as an explicit workspace artifact |
| website_highlight | Highlight a registered host element |
| website_navigate | Navigate to a registered host route |
| website_action | Invoke a host-registered action |

For a current-page question, the root instructions require website_context first.
The website guide can then call the narrower reads or actions. Website data is
untrusted source material and cannot override agent instructions or safety rules.

The host page owns authentication, authorization, DOM access, tables, figures,
manuals, and actions. The bridge exposes only structured registered resources.
Read [web_integration.md](web_integration.md) for tickets, revisions, polling,
postMessage validation, size limits, and callback contracts.

## Knowledge tools

Knowledge tools separate one-shot evidence from durable session-owned knowledge:

| Tool family | Lifecycle |
| --- | --- |
| pubmed_search, web_search, web_fetch | Collect evidence for the current run |
| evidence_index, evidence_retrieve | Index and rank current-run evidence artifacts |
| knowledge_ingest | Queue bounded public-web crawling and indexing |
| knowledge_status | Inspect an ingestion job |
| knowledge_retrieve | Retrieve cited chunks from a completed collection |
| report_synthesize | Draft from supplied evidence; it does not search |
| report_write | Save supplied Markdown; it does not synthesize |

Knowledge ingestion is durable work handled by
tools/infrastructure/knowledge. HTTP crawling and optional Scrapy execution are
private crawler implementations. Retrieval returns evidence with provenance and
session ownership.

## Approvals, guardrails, and side effects

Mark a FunctionTool with needs_approval=True only when its operation needs an
explicit user decision. In the current system:

- pipeline run and pipeline cancellation require approval;
- code_edit and code_test are direct bounded workspace operations;
- read-only tools do not require approval;
- website actions are authorized by the trusted host and its user permissions.

Approval state is serialized by the SDK as RunState. The queue stores the
pending approval and resumes the same run after an explicit decision. A tool
must not bypass an approval by calling a lower-level provider or filesystem
helper.

All public tools receive input and output guardrails. Biological safety
guardrails apply to the root and nested agents. Retrieved pages, uploaded files,
website context, and tool output are data, not instructions.

## Workspace and public boundaries

A tool may use RunContextWrapper[AgentRunContext] to access:

- the active session ID;
- the SDK sandbox session;
- workspace-relative file listings;
- the model and run metadata;
- website binding metadata when the website is connected;
- evidence and tool-result collectors.

Use workspace helpers to resolve files. Never accept a host filesystem path from
the model. Never place a secret, token, credential, or internal database path in
a FunctionResult.

Use the shared public serializer before returning provider, artifact, or runtime
data. It redacts host paths and keeps only workspace-relative paths.

## Registration checklist

When adding an atomic FunctionTool:

1. Create one focused module under tools/function_tools/<group>/.
2. Define strict input and output contracts.
3. Add the bio_function_tool decorator with a suitable timeout.
4. Resolve workspace paths through the workspace helpers.
5. Call infrastructure services or providers, not another public tool.
6. Return FunctionResult with bounded data, evidence, and relative artifacts.
7. Export the tool in tools/function_tools/__init__.py.
8. Add it to a specialist only when that specialist needs it.
9. Add representative success, invalid-input, boundary, and guardrail tests.
10. Add a prompt to docs/web_usage.md for a new user-facing capability.

When adding a specialist:

1. Define NAME, DESCRIPTION, INSTRUCTIONS, and TOOL_NAMES.
2. Use the shared specialist factory.
3. Keep the tool set narrow and non-overlapping.
4. Return a bounded summary and workspace-relative paths.
5. Register the builder in tools/agent_tools/registry.py.
6. Add a multi-step prompt and expected behavior to docs/web_usage.md.

When adding a runtime tool or pipeline:

1. Keep the runtime protocol allowlisted.
2. Define the pipeline manifest in runner.yaml.
3. Follow [pipeline_definitions.md](pipeline_definitions.md).
4. Require approval for consequential execution or cancellation.
5. Persist job status, logs, outputs, and hashes.
6. Add smoke coverage for planning and execution.

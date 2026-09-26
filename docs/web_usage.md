# Pipeline2Agent web usage

This guide describes the current web interface and the HTTP contract implemented
by interfaces/web.py. It covers the full SDK agent, session workspaces, durable
runs, atomic tools, specialist agents, pipelines, knowledge ingestion, and
trusted website embedding.

For the repository architecture, see [architecture.md](architecture.md). For
the external host-page contract, see
[web_integration.md](web_integration.md).
For pipeline manifest fields and selection metadata, see
[pipeline_definitions.md](pipeline_definitions.md).
For the other model-facing tool contracts, see
[tool_definitions.md](tool_definitions.md).

## Start the server

Set the model provider credential in the server environment, then start the
local web server:

~~~bash
conda activate openaisdk
export OPENROUTER_API_KEY="your-key"
python -B -m interfaces.web --host 127.0.0.1 --port 8000
~~~

Open one of these pages:

| URL | Use |
| --- | --- |
| http://127.0.0.1:8000 | Full workspace UI |
| http://127.0.0.1:8000/assistant | Compact assistant iframe surface |
| http://127.0.0.1:8000/assistant-demo | Trusted external-website embedding demo |
| http://127.0.0.1:8000/health | Server health check |
| http://127.0.0.1:8000/config | Public model, file, and pipeline configuration |

The default model alias is gpt-5.6-luna and the default maximum is 20 SDK
turns. The UI can select another configured model. Model aliases and provider
model IDs are defined in models/config.py.

To choose the embedding model used by new knowledge collections and evidence
indexes, set `EMBEDDING_MODEL` before starting the server. For the supported
models and re-indexing behavior, see
[Choosing an embedding model](architecture.md#choosing-an-embedding-model).

### WDL execution backend

WDL pipelines use local miniwdl and Docker by default. For the remote Mscan
Cromwell server, configure S3 input uploads and output downloads before
starting BioAgent:

~~~bash
export CROMWELL_URL=http://192.168.164.39:39000
export CROMWELL_INPUT_STORAGE_ENDPOINT=http://192.168.164.39:7070
export CROMWELL_INPUT_STORAGE_URI=s3://cncb-web-server-mic/files
export CROMWELL_INPUT_STORAGE_REGION=us-east-1
export CROMWELL_INPUT_STORAGE_MOUNT_PREFIX=/data/versitygw/data/s3
export CROMWELL_INPUT_STORAGE_ACCESS_KEY='your-s3-access-key'
export CROMWELL_INPUT_STORAGE_SECRET_KEY='your-s3-secret-key'
# Output downloads reuse the input-storage endpoint, region, and credentials.
export CROMWELL_OUTPUT_STORAGE_URI=s3://cncb-web-server-mic/cromwell/outputs
export CROMWELL_OUTPUT_STORAGE_MOUNT_PREFIX=/data/versitygw/data/s3/cncb-web-server-mic/cromwell/outputs
export CROMWELL_OUTPUT_STORAGE_EXECUTION_PATH_PREFIXES=/data/cromwell-workspace/cromwell-executions,/cromwell-share/cloud_cromwell/cromwell-executions
python -B -m interfaces.web --host 127.0.0.1 --port 8000
~~~

BioAgent uploads local inputs to S3, submits the workflow through Cromwell's
REST API, and downloads the outputs declared in `runner.yaml` from S3 after
success. Downloaded files are validated and hashed in the local job directory.
Transfer records are saved as `cromwell.input_uploads.json` and
`cromwell.output_downloads.json`.

The mount prefixes describe existing paths on the Cromwell/task hosts.
BioAgent only needs access to the Cromwell and S3 endpoints; no shared mount
is needed on the BioAgent host. Cromwell must be able to read inputs and write
outputs at those server-side paths. Reference databases remain on the task hosts.

Output downloads reuse the input-storage endpoint, region, and credentials.
Supply credentials through the environment, outside Git. Restart BioAgent
after changing these settings. New plans save the selected backend and URL;
detached workers receive the S3 transport settings.

To return to local execution:

~~~bash
unset CROMWELL_URL
python -B -m interfaces.web --host 127.0.0.1 --port 8000
~~~

### Proxy and LAN access

If OpenRouter requires a SOCKS proxy, set `AGENT_PROXY` in the same terminal
before starting the server. `ALL_PROXY` is not required when `AGENT_PROXY` is
set.

~~~bash
export AGENT_PROXY=socks5h://127.0.0.1:10801
python -B -m interfaces.web --host 127.0.0.1 --port 8000
~~~

For another computer on the same trusted LAN:

~~~bash
python -B -m interfaces.web --host 0.0.0.0 --port 8000
~~~

Find the server address with hostname -I and open
http://SERVER_IP:8000/assistant-demo or http://SERVER_IP:8000.

A local server is a development service. Put an authenticated gateway in front
of it before exposing it beyond a trusted network.

## What the web UI provides

The browser UI is a client of the same SDK runtime used by the CLI, notebook
helpers, and programmatic API.

- Sessions preserve SDK conversation history and application metadata.
- The Workspace panel lists, uploads, downloads, reads, and deletes files in
  the active session workspace.
- The assistant can reuse files and tool results across turns.
- The Runtime panel shows status, model, elapsed time, tools, files, evidence,
  and observable SDK events.
- Tool results can render Markdown, tables, figures, structure previews, and
  downloadable artifacts.
- Durable runs continue after an HTTP request or browser stream disconnects.
- Approval prompts are shown for pipeline execution and cancellation.
- The Stop control stops the browser from waiting; it does not kill an already
  running backend job.

The web UI never needs a host filesystem path. Public paths such as
uploads/sample.fasta or outputs/report.md are relative to the current workspace.

## Architecture functions visible in the UI

The main architectural functions can be tested from the chat box:

| Architecture function | How it appears |
| --- | --- |
| SDK orchestration | The root agent selects FunctionTools, specialists, and runtime tools |
| Atomic tool composition | One prompt can chain sequence, table, evidence, or workspace tools |
| Specialist delegation | Research, pipeline, document, data-analysis, coding, and website-guide specialists handle bounded multi-step work |
| Session continuity | A later prompt can refer to a downloaded or uploaded artifact |
| Durable execution | Long agent, knowledge, and pipeline work has a job ID and status |
| Native streaming | SDK events are exposed through the UI and persisted for polling |
| Approval control | Pipeline run and cancel operations pause for an explicit decision |
| Workspace isolation | Tools receive workspace-relative paths; host paths stay private |
| Knowledge lifecycle | Crawl, index, retrieve, cite, and synthesize are separate operations |
| Website bridge | The embedded assistant reads structured host context and requests host actions |
| Evidence and artifacts | Results include sources, measurements, files, and observable tool events |

## Usage examples

Use the following prompts directly in the web chat. Each prompt is designed to
exercise a specific part of the architecture and a current system capability.

### 1. Direct SDK answer

~~~text
Explain what an open reading frame is and when an ORF is biologically useful.
Do not search the web.
~~~

Expected behavior: the root SDK agent answers directly without inventing a tool
call. This demonstrates ordinary model turns and the output guardrail.

### 2. Atomic sequence analysis

~~~text
For the sequence ATGCGTAAACCCGGGTTT, calculate sequence statistics,
find ORFs, translate the forward reading frame, and return the measurements.
~~~

Expected behavior: the root composes sequence_stats, sequence_find_orfs, and
sequence_translate. The answer should distinguish each tool's result.

For a workspace file:

~~~text
Inspect uploads/sample.fasta, report its sequence statistics, and find ORFs.
~~~

The file must already exist in the active workspace. The agent should discover
or validate the workspace-relative path rather than guessing a host path.

To turn sequence features into an interactive genome map:

~~~text
Read the annotations in uploads/sample.gb, render an interactive genome map,
and return the generated map and reference paths.
~~~

Expected behavior: genome_read_features converts the GenBank annotations into a
session-owned feature artifact, then genome_render_map creates the
genome_map.json artifact and its reference sequence. The result includes an
interactive genome browser with feature colors, pan and zoom controls, feature
details on click, a full-sequence reset, and a download link for the map data.
For GFF input, provide the matching FASTA and a sequence ID when the files
contain more than one sequence:

~~~text
Read uploads/sample.gff with uploads/sample.fasta for sequence contig_1, then
render its interactive genome map.
~~~

### 3. Database retrieval and structure analysis

~~~text
Download PDB structure 1A3N as mmCIF, then inspect its chains, residues,
ligands, method, and resolution. Return the downloaded workspace path.
~~~

Expected behavior: pdb_download obtains the artifact and structure_inspect
analyzes the returned file. The artifact is reusable in later turns.

Another example:

~~~text
Look up BRCA1 in curated biological databases and return the record IDs,
organisms, descriptions, and source URLs.
~~~

This uses database_lookup and provider adapters without exposing provider
credentials or implementation paths.

To display a downloaded or uploaded protein structure in 3D:

~~~text
Download PDB structure 1A3N as mmCIF, inspect its chains and ligands, and show
the interactive 3D structure viewer.
~~~

Expected behavior: the structure artifact is rendered in the web result with
Publication, Cartoon, Stick, Sphere, and Line display styles. Drag to rotate
the model, scroll to zoom, and use the chain legend to identify chains. The
same viewer is used for AlphaFold predictions and existing workspace `.pdb`,
`.cif`, or `.mmcif` files.

### 4. Generic table analysis

Upload a CSV or TSV file, then ask:

~~~text
Profile uploads/measurements.csv. Identify numeric and categorical columns,
missing values, and suspicious ranges. Then group by cohort and plot the
measurement distributions. Save the generated figures in the workspace.
~~~

Expected behavior: the data-analysis specialist may coordinate
table_profile, table_group, and table_plot. The tools are generic table tools;
they are not restricted to biology data.

### 5. Document and workspace research

Upload a selectable-text PDF, then ask:

~~~text
Read the uploaded paper, find the sections that describe the experimental
limitations, and summarize them with page markers.
~~~

Expected behavior: document_read and workspace_search operate on the session
workspace. Scanned PDFs require OCR before their text can be read.

For multiple files:

~~~text
Search all uploaded documents for the phrase "sample preparation", then compare
the findings and cite each workspace-relative file and page marker.
~~~

### 6. Run-local web research and a report

~~~text
Research the current evidence about PhiX174 genome organization using PubMed
and trusted web sources. Fetch the most relevant pages, review the evidence,
draft a cited Markdown report, and save it to the workspace.
~~~

Expected behavior: research_specialist coordinates pubmed_search, web_search,
web_fetch, evidence operations, report_review, report_synthesize, and finally
report_write when a saved artifact was requested.

The reporting agents do not search or write independently. They receive bounded
evidence and return structured review or draft results.

### 7. Durable knowledge ingestion

~~~text
Create a session-owned knowledge collection from these trusted public sources:
https://example.org/guide
https://example.org/reference
Crawl only these domains, index the pages, and tell me the knowledge job ID.
~~~

Expected behavior: knowledge_ingest creates a durable job. It returns a
collection and job identifier rather than pretending the crawl is complete.

Then ask:

~~~text
Check the knowledge job status. When indexing succeeds, retrieve the passages
about authentication and answer with source URLs and evidence IDs.
~~~

The flow is knowledge_status, knowledge_retrieve, and citation-ready evidence.
The crawler may use the bounded HTTP crawler or the optional Scrapy subprocess.

### 8. Pipeline discovery and execution

Start with discovery:

~~~text
List the available pipelines and explain which one fits a FASTA annotation task.
Show required inputs, outputs, limitations, and example data.
~~~

Then plan and run with an uploaded file:

~~~text
Use the suitable pipeline with uploads/sample.fasta. Create a validated plan,
show the input mapping and parameters, and run it after I approve the plan.
~~~

Expected behavior: pipeline_specialist or pipeline_shell uses the
agent-pipeline protocol:

~~~text
catalog -> files -> plan -> approval -> run -> status/wait -> results
~~~

The pipeline worker verifies input hashes and output confinement. A queued or
running job is not a successful result. For a previous job:

~~~text
Check pipeline job JOB_ID and collect its verified results if it succeeded.
Do not rerun it.
~~~

### 9. Coding inside the workspace

~~~text
Inspect the Python files in the workspace, explain the current job queue design,
make the smallest edit needed to fix the status serialization, and run the
relevant bounded tests. Show changed workspace-relative files.
~~~

Expected behavior: coding_specialist can coordinate code_inspection, code_edit,
and code_test. Code editing and testing operate inside the active workspace and
do not use arbitrary host paths. Pipeline execution remains a separate,
approval-aware route.

For a read-only request:

~~~text
Find where durable run events are persisted and explain the sequence-number
contract without changing files.
~~~

This should use code_inspection only.

### 10. Trusted website guidance

Open /assistant-demo, connect the website, then ask:

~~~text
Introduce the current website. Identify the visible workflow, available tables
and figures, and the relevant manual sections.
~~~

Expected behavior: website_context is called before answering page-specific
questions. The website-guide specialist can then use
website_read_table, website_read_figure, website_search_manual, and
website_read_manual.

For structured chart interpretation:

~~~text
Read the currently visible figure, describe the axes and trends using its actual
values, and tell me which filter is active.
~~~

The bridge provides structured data from the trusted host. It does not claim
to inspect arbitrary screenshots or cross-origin DOM.

For host data analysis:

~~~text
Import the measurements table from the current website into the workspace,
profile it, and plot the distribution by treatment group.
~~~

Expected behavior: website_import_data writes an explicit UTF-8 export under
inputs/, then normal table tools analyze the imported artifact.

For a registered UI action:

~~~text
Highlight the cohort filter and navigate to the Methods section. Explain what
changed after the page revision updates.
~~~

The host validates highlight and navigation requests. The agent must use the
new page revision before reading changed resources.

### 11. Multi-turn composition

Use one session for a dependent workflow:

~~~text
Download the AlphaFold structure for the requested protein and save it.
~~~

Then:

~~~text
Inspect the latest structure, summarize its chains and confidence metadata, and
write a short Markdown report.
~~~

The second turn reuses the session workspace and conversation history. If the
file is missing, the agent should ask for the required input rather than invent
a path.

## Workspace files

The active workspace is session-scoped. Public paths use this layout:

~~~text
uploads/     files uploaded through the UI
inputs/      explicit website exports and pipeline inputs
outputs/     generated reports and ordinary artifacts
runs/        run-specific and pipeline job files
.pipeline/   private pipeline metadata
~~~

The UI displays relative paths. Internally, the runtime resolves them under
runtime/sessions/<session-id>/ and rejects absolute paths, traversal, hidden
runtime files, and symlink escapes.

Upload files through the Workspace panel or the upload endpoint. Refer to them
by the displayed relative path or by a clear filename in a prompt. Generated
artifacts remain available to later turns in the same session.

## Durable runs, streaming, and approvals

The browser normally uses POST /run_stream. The server queues the run, starts a
detached worker, and sends persisted events as SSE. A disconnected browser can
recover the same run from its ID.

For an API client, queue a run:

~~~bash
curl -sS -X POST http://127.0.0.1:8000/run \
  -H 'Content-Type: application/json' \
  -d '{"request":"Profile uploads/measurements.csv","session_id":"SESSION_ID"}'
~~~

The response contains run_id, session_id, status, model_key, and timestamps.
Read status:

~~~bash
curl -sS http://127.0.0.1:8000/runs/RUN_ID
~~~

Read events after a sequence number:

~~~bash
curl -sS 'http://127.0.0.1:8000/runs/RUN_ID/events?after=12'
~~~

Run statuses are queued, running, succeeded, failed, blocked,
pending_approval, and interrupted. Persisted event sequences make polling
resumable. SSE is a transport over the same event store, not a second agent
runtime.

Approval-controlled runs expose an approval event and pause at
pending_approval. Submit an explicit decision:

~~~bash
curl -sS -X POST http://127.0.0.1:8000/approve_stream \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"SESSION_ID","approved":true,"approval_id":"APPROVAL_ID"}'
~~~

Pipeline run and cancellation require approval. Code inspection, code editing,
and bounded code tests use their direct workspace tool path.

## HTTP endpoints

### Browser and session endpoints

| Method and path | Purpose |
| --- | --- |
| GET / | Full workspace UI |
| GET /assistant | Compact embedded assistant page |
| GET /assistant-demo | Canonical trusted website demo |
| GET /health | Health response |
| GET /config | Model, artifact, and pipeline configuration |
| GET /sessions | List sessions and message counts |
| GET /sessions/<id>/messages | Read displayable session messages |
| PATCH /sessions/<id> | Update title or pinned state |
| DELETE /sessions/<id> | Delete SDK history, metadata, and workspace |

### Run endpoints

| Method and path | Purpose |
| --- | --- |
| POST /run | Queue a durable run and return its identifier |
| POST /run_stream | Queue a run and stream persisted events as SSE |
| GET /runs | List recent runs, optionally filtered by session_id |
| GET /runs/<id> | Read one run status and public result |
| GET /runs/<id>/events?after=N | Read resumable events |
| POST /approve | Resume an approval through the synchronous API |
| POST /approve_stream | Queue approval resume and stream persisted events |

### Workspace and knowledge endpoints

| Method and path | Purpose |
| --- | --- |
| GET /workspace?session_id=<id> | List session files and capabilities |
| GET /workspace/file?session_id=<id>&path=<relative-path> | Read/download one file |
| POST /workspace/files | Multipart upload into the session workspace |
| DELETE /workspace/files/<path>?session_id=<id> | Delete one workspace-relative file |
| GET /knowledge/jobs/<id>?session_id=<id> | Read knowledge job status |
| GET /knowledge/jobs/<id>/events?session_id=<id>&after=N | Read ingestion events |
| GET /knowledge/jobs/<id>/stream?session_id=<id> | Stream ingestion events as SSE |

### Website bridge endpoints

The website bridge endpoints are documented in
[web_integration.md](web_integration.md):

| Method and path | Purpose |
| --- | --- |
| POST /website/demo-token | Issue a local demo ticket |
| POST /website/connect | Bind a trusted host page to a session |
| POST /website/context | Replace the host page snapshot |
| POST /website/poll | Poll pending host callback requests |
| POST /website/respond | Return a correlated host callback result |
| POST /website/disconnect | Revoke the binding |

The browser assistant then includes the website binding in POST /run or
POST /run_stream. The binding does not remove any existing root tools.

## Embed the assistant in a trusted website

The canonical local demonstration is /assistant-demo. A real host website should
use the same iframe helper but provide its own authenticated ticket endpoint and
host adapter:

~~~html
<div id="agent-root"></div>
<script src="https://agent.example.com/static/assistant-embed.js"></script>
<script>
  const assistant = AssistantDrawer.mount({
    target: document.getElementById("agent-root"),
    src: "https://agent.example.com/assistant",
    siteId: "lab-portal",
    getToken: async () => {
      const response = await fetch("/assistant-token", {method: "POST"});
      return (await response.json()).token;
    },
    adapter: {
      getPageContext: async () => pageSnapshot(),
      readTable: async ({resource_id, offset, limit}) =>
        tablePage(resource_id, offset, limit),
      readFigure: async ({resource_id}) => chartDescription(resource_id),
      searchManual: async ({query, limit}) => manualSearch(query, limit),
      readManual: async ({section_id}) => manualSection(section_id),
      exportData: async ({resource_id}) => exportResource(resource_id),
      highlight: async ({element_id, message}) =>
        highlightRegisteredElement(element_id, message),
      navigate: async ({route_id}) => openRegisteredRoute(route_id),
      invokeAction: async ({action_id, arguments: args}) =>
        runRegisteredAction(action_id, args)
    }
  });
</script>
~~~

getPageContext is required. Implement only callbacks supported by the host.
Use stable resource, route, element, and action IDs. Return structured JSON,
not arbitrary DOM or screenshots. The host owns authentication and must enforce
the logged-in user's permissions.

Configure exact trusted origins:

~~~bash
export AGENT_WEBSITE_SITES='{"lab-portal":["https://lab.example.com"]}'
export AGENT_WEBSITE_SECRET='a-long-random-shared-secret-at-least-32-characters'
~~~

The signing secret stays on the server. The browser receives a short-lived
ticket and then a session-scoped binding token. Website data is imported into
the normal workspace only through an explicit website_import_data operation.

Read [web_integration.md](web_integration.md) before deploying an
external integration. It defines revisions, callback limits, polling,
postMessage origin checks, ticket replay protection, and idempotency.

## Troubleshooting

Port 8000 already in use:

~~~bash
ss -ltnp 'sport = :8000'
ps -eo pid,cmd | rg 'interfaces\\.web|interfaces/web.py'
kill PID
~~~

Website connection says that the origin is not configured:

1. Copy the browser origin exactly, including scheme, hostname, and port.
2. Add it to AGENT_WEBSITE_SITES under the correct site ID.
3. Restart the server.
4. Reload /assistant-demo or choose Retry website connection.

The assistant answers about a website without consulting it:

1. Confirm the website connection indicator is active.
2. Ask for the current website or visible figure explicitly.
3. The runtime instruction requires website_context for page-specific questions.
4. If the binding expired, reconnect the host page.

A run appears stuck:

1. Read GET /runs/<id>.
2. Read GET /runs/<id>/events?after=N.
3. Check whether it is queued, running, pending_approval, or interrupted.
4. Do not submit another request for the same side effect automatically.
5. Review a failed or interrupted pipeline job before deciding whether to create
   a new plan and retry.

## Safety and deployment notes

- Keep OPENROUTER_API_KEY, AGENT_WEBSITE_SECRET, and provider credentials out
  of source control and browser payloads.
- Treat crawled pages, uploaded documents, and website data as untrusted data.
- Public responses expose workspace-relative paths, never host filesystem paths.
- The pipeline shell accepts only the allowlisted agent-pipeline protocol.
- Knowledge crawlers use bounded public HTTP/Scrapy access; they are not a
  general private-network browser.
- The local server does not provide complete multi-user authorization. Use an
  authenticated reverse proxy or application gateway for shared deployments.
- Durable workers do not silently replay interrupted side effects.

For implementation changes, update [architecture.md](architecture.md),
[web_integration.md](web_integration.md), and the relevant smoke tests
together.

# Web bridge

This package owns the external-website connection: identity mapping, embedded
sign-in, page callbacks, conversations, file-transfer endpoints, result access,
browser SDK and reference website adapters. It runs inside the existing agent
server and workers; it does not start a separate agent execution service.

## Organization

```text
web_bridge/
├── __init__.py                 # Public application integration hooks
├── config.py                   # Clients, secrets and exact trusted origins
├── identity.py                 # External identities and single-use login grants
├── bridge.py                   # Bindings and durable browser callbacks
├── conversations.py            # Website sessions, provenance and result links
├── delivery.py                 # Persistent delivery queue, sharing and receipts
├── http.py                     # Service, browser and login-exchange endpoints
├── ports.py                    # Host account/session/storage interfaces
├── browser/                    # SDK-independent host-page observation service
├── transfer/                   # Independent chat-driven transfer commands
├── adapters/
│   ├── bioagent.py              # Existing account, session, file and run services
│   └── mscan/                   # Reference website adapter and installer
├── frontend/
│   ├── embed.ts                # Single source for the website embedding SDK
│   ├── build.mjs               # Produces /static/assistant-embed.js
│   ├── WebsiteProvider.tsx     # Cookie-free iframe sign-in
│   ├── useWebsiteBridge.ts     # Iframe protocol, callbacks and connection state
│   ├── observer.ts             # Generic DOM observation, tables and route changes
│   └── demo/                   # Generic host-page example
└── tests/                      # Protocol, HTTP, dependency and live tests
```

## Dependency boundary

The protocol, identity, conversation and endpoint code imports only this package
and Python's standard library. It calls the `HostServices` interface in
`ports.py` for account, session, run and file operations. It does not import
`harness.runtime`, `interfaces.api`, `auth`, or `isolation` directly.

`adapters/bioagent.py` supplies those operations using the existing services.
Agent-facing definitions live in `tools/function_tools/website/`; the website
specialist and root-agent website instructions live in
`tools/agent_tools/specialist/website_guide.py`. They use the existing tool
contracts, decorators and guarded specialist factory directly. Bridge services
remain independent of the Agents SDK and can be called by other modules.

The bundled BioAgent adapter is loaded lazily in each process. Another agent can
provide its own adapter through `web_bridge.configure_host(adapter)`; the
protocol test exercises this with all BioAgent imports blocked. Detached workers
must configure the same adapter in their own process when using a custom host.

Identity transactions deliberately use the existing auth SQLite connection so
consuming a login grant and creating its login remain atomic. Core bridge code
manages only bridge-owned tables; account-table access stays in the adapter.
The separate bridge SQLite database retains callbacks and conversation links.

## Application connection points

- `interfaces/web.py` delegates bridge routes and response headers to the public
  API. `interfaces/auth.py` runs bridge service/grant handlers after its normal
  origin checks and notifies the module on logout.
- `interfaces/api.py` validates the binding, records run provenance, and applies
  legacy message normalization through the public API.
- `harness/runtime.py` carries the private binding and adds the module's run
  guidance only when a website is connected.
- The existing tool registries import `WEBSITE_TOOLS` from
  `tools/function_tools/website/` and the guide specialist from
  `tools/agent_tools/specialist/website_guide.py`.
- The ordinary assistant page mounts `WebsiteProvider` and `useWebsiteBridge`.
  Chat rendering, uploads, run progress and cancellation remain in the assistant.

Accounts, isolated execution, pipeline execution and general message renderers
remain owned by their existing modules. Website adapters do not duplicate them.
The bridge HTTP handlers use the server's JSON request/response methods; streamed
workspace downloads go through the host adapter.

## Build and use

```bash
npm --prefix frontend run build
docker build -f isolation/deploy/Dockerfile -t bioagent-worker:local .
```

The build uses `frontend`'s existing Vite/TypeScript dependencies. Both the generic
demo and the downloadable SDK use `frontend/embed.ts`; there is no second
hand-edited JavaScript implementation. The generated SDK remains at
`frontend/dist/static/assistant-embed.js` and the public URL is unchanged.
Frontend development forwards `/static` to the agent, so build the SDK before
using a new checkout's development server.

See the [protocol and API guide](../docs/web_integration.md) and
[MSCAN setup](adapters/mscan/README.md). MSCAN's canonical adapter sources are
here because the development checkout under `resource/` is ignored by Git.

```bash
python web_bridge/adapters/mscan/install.py
python web_bridge/adapters/mscan/run.py agent
# In separate terminals:
python web_bridge/adapters/mscan/run.py backend
python web_bridge/adapters/mscan/run.py frontend

# Explicit identity linking, with the server's configuration/environment:
python -m web_bridge.identity SITE_ID EXTERNAL_USER_ID AGENT_USERNAME
```

## Compatibility

This reorganization preserves HTTP URLs, message protocol, tool names,
environment-variable names, database paths, table layouts and existing identity,
session and artifact records. No data migration is required. Pipeline definitions
are not part of this module and were not moved or edited.

Python import paths and developer CLI paths have moved. The old implementation
files in `auth/`, `harness/`, `interfaces/` and the website tool folders are removed;
use this package instead. Update custom launch scripts to the commands above.

## Verification

```bash
python -B -m unittest discover -s web_bridge/tests -t . -p 'test_*.py' -q
python -B -m evals.smoke_architecture
python -B -m evals.check_web_multitasking

# Opt-in live checks: running MSCAN/agent, real model calls and remote template WDL.
python -B -m web_bridge.tests.check_mscan --pipeline
python -B -m web_bridge.tests.check_mscan --pipeline-only --detach
python -B -m web_bridge.tests.check_mscan_logout
```

The core boundary test rejects direct imports of host implementation modules.
Protocol/HTTP tests cover ownership, identity grants, replay, origins, persisted
bindings, checksums, resumable uploads, downloads and logout. Live test assumptions
and evidence locations are documented with the MSCAN adapter.

### Refactor validation — 2026-11-04

- Regression suite: 121 tests run, 118 passed and 3 skipped. Includes bridge
  protocol/HTTP/boundary tests, isolation, pipeline completion, tool compatibility,
  uploads, history and web contracts.
- Frontend production build, worker Docker build, architecture smoke test and
  browser multitasking checks passed.
- Live MSCAN acceptance: all 10 checks passed, including cross-site cookie-free
  sign-in, table/chart callbacks, CSV/report creation, restored conversations,
  SHA256-verified file transfer, idempotent import, sign-in renewal, Stop, remote
  template WDL completion/results and logout revocation. Evidence:
  `runtime/live-validation/bridge-refactor/checks.json`.
- Generic demo connected, synchronized a changed cohort and reopened its drawer
  using the same SDK. The Spring logout event probe also passed.

MSCAN was tested with its existing development login bypass. Production CAS
sign-in still needs acceptance with real accounts when that bypass is disabled.

## Page, resource and result interoperability

The SDK observes the actual rendered host DOM and detects route, text, table and
control changes. Page-specific context callbacks are optional enrichment. The
assistant can call `website_observe` on pages without registered context. Hosts can expose
`listResources` (stable IDs, kinds, pagination and availability) and
`importResource` (stream a selected file through the backend upload API).
`website_list_resources` and `website_import_resource` make these operations
available to the agent. Raw files and previously received outputs use chunked
transfer; the small inline text-export protocol remains available for tables.

For automatic delivery, publish an optional `delivery_target` object in page
context. The bridge records this object when a run starts. The target is opaque
to the generic bridge; its meaning and ownership checks belong to the receiving
website. Navigating elsewhere does not change the saved destination. Runs without
a destination can be handed off explicitly through `website_push` in ordinary
chat. The agent UI has no transfer buttons. The old one-use share API is retained
for compatibility; new integrations should use the command protocol below.

`delivery.py` keeps durable pending deliveries in the existing bridge database.
The website backend polls `POST /website/service/deliveries`, downloads only the
manifest's artifacts through `GET /website/service/delivery-artifact`, persists
its files and receipt, then calls `POST /website/service/delivery-ack`. All three
operations require the site's server credential. Delivery uses leases, retry
backoff and stable IDs; an expired worker cannot acknowledge a replacement lease.
Remote pipeline artifacts stream through the existing artifact server. Plain
answers without output files and unsuccessful runs are not published as analyses.
The browser does not participate in delivery.

MSCAN's receiver stores artifacts and receipts under `BIOAGENT_RESULTS_ROOT`
(default `./data/agent-results` relative to its backend; the launcher uses
`runtime/website-integration/mscan-results`). This storage belongs to MSCAN and
should be persistent and backed up. Each receipt records the owning external
user, target sample, agent run, filenames, sizes and computed SHA256 checksums.
Repeated delivery IDs reuse the committed receipt. Its native downloads use
single-use, sixty-second tickets; file and sample ownership is checked before
issuing and consuming them.

The MSCAN adapter recognizes the QC pipeline's `qc_counts.tsv` / input-count TSV
format and updates the existing three QC read-count fields after validating the
counts. Older completed deliveries do not replace newer QC metrics. Other output
formats remain available as attached files under **Agent results → Received by
MSCAN** and can be imported back into an agent conversation. Native interpretation
of another pipeline's domain-specific results belongs in the MSCAN adapter;
the generic bridge transports its files without requiring such interpretation.

The installer adds only the adapter mount/context hook, a result-refresh hook,
logout hook, and the one-use download route to MSCAN's existing application.
Source pipeline definitions and execution policies are unchanged.


### Interoperability verification — 2026-11-04

The expanded regression suite ran 135 tests: 132 passed and 3 were skipped.
Live checks used the existing MSCAN development login bypass and its explicitly
linked agent account. Navigation, automatic raw-file import, remote QC with the
browser closed, durable receipt, native QC fields, standalone sharing, one-use
native download tickets and importing a received output back into the agent were
exercised. QC returned 4,168 input reads, 4,168 after QC and 4,149 after host removal.
Evidence is under `runtime/live-validation/bridge-complete/`.

The Java probes exercise the adapter logout hook, scoped download security and native QC parsing, including
invalid/incomplete counts. The delivery tests cover site/user ownership, share
replay, pinned targets, remote artifacts, leases, retries and empty/failed runs.

To repeat the full QC flow against a selected development sample:

```bash
python -B -m web_bridge.tests.check_mscan_interoperability \
  --url http://127.0.0.1:8848/sample/metagenomic \
  --agent-url http://127.0.0.1:8000 --sample-name detection_demo
```

This opt-in command makes paid model calls, runs the real QC pipeline, and updates
that sample's MSCAN QC metrics through the receiver.

## Independent browser and transfer modules

```text
web_bridge/
  browser/service.py       SDK-independent host-page observation
  frontend/observer.ts     generic DOM observer in the user's host tab
  transfer/service.py      durable commands, ownership, leases, upload grants
  adapters/mscan/
    data_transfer/
      AssistantTransferService.java  MSCAN discovery, destinations, source registration
      AssistantDeliveryService.java  verified file delivery and durable receipts
    result_importers/                format registry, native imports and QC parsing
    resources/                       native result discovery and downloads
```

The agent-facing layer is owned by the main tool system:

```text
tools/
  function_tools/website/
    __init__.py             WEBSITE_TOOLS collection
    page.py                 page context, resources, tables and actions
    browser.py              website_observe tool
    transfer.py             chat-driven search/pull/push/status/retry
  agent_tools/specialist/
    website_guide.py         guide specialist and root website instructions
```

Dependencies flow from the agent through `tools/` into `web_bridge/` services.
Account linking, transfers, browser communication and site adapters stay in the
bridge; other modules can use those services without tool decorators.

The browser SDK reads rendered text, headings, controls and HTML/ARIA tables.
It observes DOM changes and URL changes automatically. `observePage` supplies a
fresh snapshot; `getPageContext` adds optional structured metadata. A failed
structured callback does not prevent observing the page. `dom:*` table handles
work with existing table-read/export tools. Large tables are paginated and
exports identify partial data. Password inputs, hidden content and the assistant
UI are excluded. Images/canvas are identified, but their pixels are **not** read;
cross-origin iframe content and closed shadow roots are not traversed. The SDK
must be installed on the external site to observe the user's actual tab. It does
not silently connect to an arbitrary browser or copy browser login cookies.

Backend transfer works without a browser tab and without a website conversation.
The ordinary agent account must have an explicit external identity link. Tools:

- `website_connections`: list linked sites, destination fields and backend capabilities.
- `website_search`: search owned projects, samples and downloadable resources.
- `website_pull`: copy a resource into the current isolated session.
- `website_push`: send selected session files to a website-defined destination.
- `website_transfer_status`: obtain a final receipt or a specific failure.
- `website_transfer_retry`: resume a failed command under its original ID.

For MSCAN, `website_push.destination_json` contains a JSON object such as
`{"project":"My project","sample":"Sample A","data_type":"meta"}`.
Optional `source_slots` maps `R1`/`R2` or `genome` to selected workspace paths.
A single sequence file can be assigned automatically; multiple sequence outputs
remain attached results unless source roles are supplied. Missing named projects
and samples are created when `create_missing` is true. Ambiguous names require
IDs. Existing source slots are preserved and reported as `results_only`.
Registration does not launch a native MSCAN pipeline or invent sample metadata.

Examples of user requests:

> Pull the R1 FASTQ from my detection_demo sample in MSCAN.
>
> Push this report and these reads to MSCAN project “November study”, sample
> “Sample A”. Create the project and sample if necessary.

The generic queue treats destination fields as opaque; each website adapter
implements its own entity creation and permissions. The site backend polls with
its private service credential, receives a verified external subject, reads only
selected artifact paths, and streams pull uploads through a command-specific
grant. It cannot enumerate unrelated standalone sessions. Leases renew during
long transfers; after a backend crash the same command can resume after expiry.
Retries reuse IDs, files and destination records. Browser/model code never sees
the service secret. MSCAN currently processes one transfer at a time; agent chats
and pipelines remain independently concurrent.

| Service endpoint | Contract |
|---|---|
| `POST commands` | Advertise optional `capabilities` and lease one queued command for the authenticated site |
| `POST command-heartbeat` | Renew its current ID/lease for 120 seconds |
| `POST command-ack` | Persist success/result or failure; current lease required |
| `GET command-artifact?id=...&path=...` | Stream only a selected push artifact |
| `POST uploads` with `command_id` | Grant a pull upload to its exact owner/session |

All paths use the `/website/service/` prefix. Commands include `id`, `subject`,
`session_id`, `operation`, `payload` and `lease`. Search results contain paginated
`resources`; pull results contain the completed workspace `file`; push results
contain destination IDs, a stable receipt and source-registration status. Sites
must store a receipt before acknowledging and handle repeat command IDs.

## Latest live acceptance

The modular observer/transfer update was exercised against the running agent
and MSCAN development deployment. Evidence is in
`runtime/live-validation/bridge-modular/summary.json` (ignored runtime data).
Tests covered real model-driven push/search/pull, native destination creation,
FASTQ and report roundtrips, paired source roles, FASTA registration, source
preservation, a failed-command retry, lost-ack replay, checksums, native sample
visibility and live SPA navigation. The generic browser test also exercises a
page with no registered adapter and a failing optional structured-context hook.
The bridge suite passes 42 tests; architecture, frontend, Maven and worker-image
build checks pass. These checks used MSCAN's development login bypass, not
production CAS authentication.

## Native MSCAN QC import and embedded presentation

Push accepts owned remote `pipeline-artifacts/...` files and generated
`pipeline-bundles/<job>/results.zip` archives. The BioAgent host adapter validates
bundle ownership against the session's completed job; ZIP size is determined
while streaming. Selecting a pipeline bundle also includes its individual,
manifest-owned outputs, deduplicated against explicitly selected files. This
lets connectors import native results even when the agent selects only the ZIP.
Remote outputs do not need a local workspace copy first. Pipeline outputs are
marked separately from source files; MSCAN only uses them as raw inputs when
explicitly assigned through `source_slots`.

MSCAN's QC importer stores clean reads and the summary in its object storage,
creates an owned `qc_result` record, updates native read counts, and records the
QC program as completed. Push responses include `native_qc_applied` and the
imported counts, separately from the file-delivery receipt. This makes the sample visible in QC-filtered lists and
lets native workflows resolve the clean-read paths. Received files are available
from **Download files** on the sample toolbar. The floating **Agent results**
panel is removed. The embedded agent hides Runtime/Plan/Evidence/Trace details;
the standalone agent retains those panels and both retain approval controls.

## Analysis result exchange

The generic transport carries files and optional `pipeline_result` provenance
(job ID, pipeline name, output key/kind and completion time). Provenance is
resolved from the owner's durable job manifest, never from model-supplied paths
or credentials. Bundles include available individual outputs, skipping absent optional outputs; local output selections are
checked against their recorded checksum. The transport has no MSCAN program list.

MSCAN-specific code is [organized by function](adapters/mscan/README.md#code-organization).
The [minimal installation](adapters/mscan/README.md#minimal-mscan-changes) modifies
only two existing frontend files; backend integration is supplied by added adapter classes.
Native importers live in `adapters/mscan/result_importers/`:

- `ResultImporterRegistry` declares format contracts and binds MSCAN's existing
  native parsers.
- `ResultImportService` groups outputs by job, validates the sample
  type and required roles, stages objects, and invokes MSCAN's existing parsers
  inside a database transaction. Newer completed native results are preserved.
- `QcResultImporter` parses QC reports and writes native QC/status records.
- `NativeImportContext` supplies only that import's stored output metadata to
  the parser on the current thread. It clears its context on success or failure;
  importing a result cannot submit another workflow.
- `resources/NativeResultResources` exposes owned object-storage files from QC,
  assembly, functional annotation, classification, annotation, bacterial-system
  and SNP records for search, downloads and natural-language pulls. Each resource
  resolution rechecks sample ownership and the native row. Structured native
  records (including QC metrics, growth estimates and profiles) are also
  downloadable and pullable as JSON, so numerical results need not have an
  original artifact file.

Registered native formats:

| Output namespace | MSCAN program | Sample types |
| --- | --- | --- |
| `MetagenomicQc`, `ReadQc` | QC (existing counts importer) | meta, shortReads |
| `AssemblyId` | assembly | meta, shortReads |
| `metax` | metax | meta, shortReads |
| `FuncReads` | funcflow | meta, shortReads |
| `FuncAssembly` | funcflow | genomic, synthetic |
| `StrainMeta` | strain_meta | meta, shortReads |
| `StrainCoPTR` | growth | meta, shortReads |
| `BacDef`, `BacSec`, `BacBGC` | bacdef, bacsec, bacbgc | all four types |
| `PhiAnnotatorGenome`, `TcdbAnnotatorGenome` | phi, tcdb | genomic, synthetic |
| `PhiAnnotatorMetagenome`, `TcdbAnnotatorMetagenome` | phi, tcdb | meta, shortReads |

QC accepts both the three-metric key/value report and the single-sample
`ReadQc` summary table; clean-read roles come from output provenance, so renaming
a file does not break registration. Multi-sample summary tables require explicit
splitting into sample-specific transfers.

The connector advertises required output roles through `website_connections`.
These registrations describe import contracts, not execution restrictions or a
claim that every existing pipeline has a matching MSCAN table. Other pipelines,
including custom shell/Nextflow/Snakemake pipelines, can still exchange files.
Unknown formats remain attached files with an explicit `unsupported` native
import status. Do not guess native mappings from filenames or mark a program
successful merely because its ZIP was received.

Push responses separate `file_delivery` from per-job `native_imports`:
`imported`, `incomplete`, `incompatible_sample_type`, `unsupported`, `superseded`
or `failed` (QC can also report `not_imported`). Missing output roles are listed. A parser failure rolls back its
native database changes and fails the transfer while retaining the received
files and error details. Retrying that transfer reuses its receipt and destination
and skips already committed native imports. Corrected output content requires a
new transfer. QC also retains its `native_qc_applied` field for compatibility.

Downloads appear beside the selected sample across native analysis tabs; there
is no separate Agent results panel. Natural-language push/pull stays in the
agent, with no transfer buttons on the agent page.

### Runtime dependencies and verification

MSCAN's table importers use its existing DuckDB/Parquet service. Install the
`httpfs` extension matching the bundled DuckDB JDBC version before serving
imports. Configure `duckdb.extension-directory` to that cache and
`duckdb.httpfs.auto-install: false` to avoid network installation while a native
import transaction is open. A missing dependency is an import failure, not a
successful analysis result.

Run the repeatable live fixture test with the same environment as the agent:

```sh
python -B -m web_bridge.tests.check_analysis_imports --username YOUR_TEST_USER
```

This writes clearly named test projects/samples, a session and small synthetic
import fixtures; it does not execute biological pipelines. The account must
already be linked to a running MSCAN connector. It checks source registration,
native import and pull across the four sample types and registered formats, plus
incomplete, incompatible and unknown formats, failed-import retries, older-result
preservation and structured JSON exports. Live validation also imported the user's
already-completed remote assembly output and verified its native page and file
round trip. Fixture checks exercise import contracts rather than biological computation.
Production data should still be validated against those contracts; passing an
import test is not a blanket end-to-end pipeline guarantee.

The native ownership/field checks and QC parser checks can run without services,
after building the installed MSCAN adapter (JDK `java` and `javac` on `PATH`):

```sh
python -B -m web_bridge.tests.check_mscan_java
```

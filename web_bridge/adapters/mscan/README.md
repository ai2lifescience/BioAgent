# MSCAN reference adapter

MSCAN keeps its database, login, storage and workflow service. BioAgent keeps its
accounts, conversations, isolated workers, files and durable run queue. This
adapter connects them through the [generic web bridge](../../../docs/web_integration.md).
Other websites implement the same small backend and browser adapter contracts.

## Code organization

Canonical adapter sources are grouped by responsibility:

```text
mscan/
├── connection/                 # Embedded assistant, navigation context and logout
│   ├── AssistantBridge.vue
│   ├── context.ts
│   ├── logout.ts
│   ├── WebsiteLogoutEvent.java
│   ├── WebsiteLogoutHook.java
│   └── WebsiteDownloadSecurity.java
├── data_transfer/              # Push/pull commands, file delivery and receipts
│   ├── AssistantTransferService.java
│   ├── AssistantDeliveryService.java
│   └── TransferLocks.java
├── result_importers/           # Translate received outputs into native records
│   ├── ResultImporterRegistry.java
│   ├── ResultImportService.java
│   ├── QcResultImporter.java
│   ├── ResultArtifactInspector.java
│   ├── ImportFailure.java
│   └── NativeImportContext.java
├── resources/                  # Discover, read and download native results
│   ├── NativeResultResources.java
│   ├── SampleFileMenu.vue
│   └── sampleFiles.ts
├── tests/                      # Java ownership, QC and logout checks
├── AssistantController.java    # Host HTTP endpoints and identity checks
├── install.py                  # Copy adapter sources and install host hooks
└── run.py                      # Development configuration and launch helper
```

[`ResultImporterRegistry`](result_importers/ResultImporterRegistry.java) owns the
format contracts: sample types, required output roles and existing MSCAN parser
bindings. [`ResultImportService`](result_importers/ResultImportService.java)
handles import orchestration, transactions, retries, per-job outcomes and
preservation of newer results. [`QcResultImporter`](result_importers/QcResultImporter.java)
parses QC summaries and writes native QC records. Other formats reuse MSCAN's
existing parsers through [`NativeImportContext`](result_importers/NativeImportContext.java).
Add a supported native format in the registry; ordinary file exchange does not
require a native importer.

`ResultArtifactInspector` adds bounded TSV/CSV/JSON/text previews to delivered
file metadata, independently of pipeline names. Search returns this metadata;
pull returns the complete, unchanged file. Binary and unfamiliar formats remain
downloadable. The preview reads at most 64 KiB and shows at most three table rows;
these are preview limits, not upload or result-size limits. Previews are untrusted
file content and must not be treated as instructions.

Each per-job receipt separates `generic_import` (files attached to the sample)
from its native `state` (MSCAN records). An unknown format can have a successful
generic import and an `unsupported` native state. Missing roles and incompatible
sample types are not silently repaired or reported as native success. Native
views still require a registered, validated result contract; an LLM does not
invent values or write database records.

The registry includes `MashIdentify` and `StrobeTaxaDetection`, using MSCAN's
existing result parsers through import-only service entry points. Repeated WDL
output roles are preserved as arrays; scalar roles required by a native parser
must remain unambiguous. Header-only growth CSVs report `empty` and preserve
existing native results. A transactional postcondition also rolls back growth
imports when the native parser produces no valid records. Templates and unknown formats remain downloadable
attachments with an explicit `unsupported` native state.

`ImportFailure` reports stable error codes without exposing raw SQL, proxy
credentials or storage secrets. For `storage_proxy_configuration`, normalize
HTTP(S) proxy URLs (for example `http://127.0.0.1:10801`, without `/`), restart the
MSCAN backend and retry the failed transfer. `run.py backend` performs this
normalization automatically; the everyday startup exports in the installation
guide do the same for direct `java -jar` startup. Existing delivered files are
retained and native import retry does not repeat committed QC.

[`AssistantDeliveryService`](data_transfer/AssistantDeliveryService.java) downloads
and verifies files, delegates native import, and persists receipts.
[`AssistantTransferService`](data_transfer/AssistantTransferService.java) handles
transfer commands and destination creation.
[`NativeResultResources`](resources/NativeResultResources.java) resolves owned
native files and structured JSON exports for search, pull and download.
Connection code manages the embedded browser integration and logout.

These folders organize the **adapter source**, while the installer retains
MSCAN's existing Java package and frontend integration paths. This avoids moving
host application packages or changing its API routes. Rerunning the installer
removes only the renamed adapter classes and their stale compiled output, so
older Spring beans cannot remain beside their replacements. Generic bridge
identity and transfer code stays outside this MSCAN adapter.

## What is connected

- MSCAN's current user maps to a stable BioAgent identity. The embedded assistant
  signs in automatically without passwords or third-party cookies.
- The selected sample, active results tab and filters become versioned page
  context. The assistant can read visible tables, QC figures and a short guide.
- Native analysis views show supported imported records; the sample toolbar
  provides a Download files menu across analysis tabs.
  Reloading MSCAN restores the current assistant conversation. Runs and artifacts persist
  even when the browser is closed.
- Natural-language `website_pull` commands stream authorized sample files from MSCAN
  object storage into the current agent session. Size limits, ownership, retry
  offsets and SHA256 verification apply. Repeating a source/revision import
  reuses the existing artifact. The source file is unchanged.
- Reports and other agent artifacts download from either UI. They remain agent
  artifacts; registered result formats also update native analysis records. Source files
  can be registered against a new sample; existing source slots are preserved.
- The embedded Stop button cancels the actual server run. Ordinary tools and
  pipelines use the existing agent execution service and isolation configuration.

## Install

See the [installation guide and exact MSCAN file changes](../../../docs/mscan_web_bridge.md#install-the-web-bridge-in-mscan)
for prerequisites, setup, builds, startup and verification.

Run from the BioAgent repository root. The MSCAN checkout is expected at
`resource/mscan/{mscan,mscan-app}`; supply a different root if needed.

```bash
python web_bridge/adapters/mscan/install.py
python web_bridge/adapters/mscan/run.py init --origins http://localhost:8848,http://127.0.0.1:8848,http://YOUR_SERVER_IP:8848
npm --prefix frontend run build
docker build -f isolation/deploy/Dockerfile -t bioagent-worker:local .
cd resource/mscan/mscan-app
mvn clean package -DskipTests
```

Use an actual IP instead of `YOUR_SERVER_IP`. The installer copies the canonical
adapter sources in this directory and changes three existing frontend files:
`src/App.vue` mounts the assistant; `src/views/sampleProgramResults/index.vue`
connects selected sample context, result refreshes and the download menu.
`src/views/sampleProgramResults/components/ProgramResultPanel.vue` changes one
condition so synthetic samples use the assembly-results component that matches
their native records.
Four backend files receive two import-only entry points: `IGenomeTracingService`
and its implementation expose `importDetectionResult`; `IMetadataProcessService`
and its implementation expose `importKmerDetectionResult`. These call the
existing result parsers without running a poller or submitting a workflow.
Installation preserves host line endings and does not reformat whole files.
Since `resource/` is ignored, these tracked sources and the installer are the portable
integration deliverable. No MSCAN database migration is required.

Activate the environment providing Java, Maven, Node/pnpm and agent Python first
(for this development checkout, `conda activate openaisdk`). Install each project's
dependencies as usual. `init` creates a private runtime config, retains existing
keys on rerun and updates the allowed origins. Do not commit that file.

## Minimal MSCAN changes

Compared against the original `resource/mscan.zip` and `resource/mscan-app.zip`:

| Existing host files | Bridge changes |
| --- | --- |
| Frontend `src/App.vue` | Import and mount the embedded assistant |
| Frontend `src/views/sampleProgramResults/index.vue` | Sample context, result refresh and download menu |
| Frontend `src/views/sampleProgramResults/components/ProgramResultPanel.vue` | One condition selects assembly results for synthetic samples |
| Backend `IGenomeTracingService` and implementation | One import-only entry point delegates to the existing genomic identification parser |
| Backend `IMetadataProcessService` and implementation | One import-only entry point delegates to the existing k-mer identification parser |
| Database schema, workflow and existing security files | None |
| Existing frontend user store and QC panel | None |

The remaining integration files are additions owned by this adapter: five
frontend files under `src/integrations/bioagent/` and Java files under the admin
module's `com.mscan.web.controller.common` package. `WebsiteDownloadSecurity`
adds a higher-priority chain scoped only to GET `/assistant/received-download/*`;
the controller still validates the one-use ticket and resource ownership. Other
routes continue through MSCAN's original security chain. Adapter backend beans
are conditional on `bioagent.enabled=true`.

The installer also removes exact legacy bridge patches from the user store,
CAS configuration and security configuration when upgrading an older installation.
It preserves unrelated customizations. The local `pnpm-workspace.yaml` contains
an earlier package-manager setup fix (`packages: ['.']`); this is separate from
the bridge and is not applied by the installer. Supply normal dependency and
runtime configuration for your deployment, then rebuild and restart services.

Reproduce the clean installation check using the original ZIPs:

```bash
python -B -m web_bridge.tests.check_mscan_install
# Keep a clean installed copy for a separate Maven/frontend build:
python -B -m web_bridge.tests.check_mscan_install --destination /tmp/mscan-clean
```

The check compares all original files byte for byte and verifies that a second
installation produces no further changes. It does not run biological workflows
or use the production database. The destination must not already exist.

## Run

For normal `python -m interfaces.web`, `java -jar` and `pnpm dev` startup, see
[Everyday startup](../../../docs/mscan_web_bridge.md#everyday-startup). Export the
bridge settings in the agent and backend terminals using the existing private
client configuration. Direct Java startup preserves MSCAN's normal scheduler settings.
The commands below are an optional launcher alternative.

From the repository root, use three terminals. Keep your existing model,
Cromwell and object-storage environment variables in the agent terminal.

```bash
# Terminal 1: agent, port 8000
python web_bridge/adapters/mscan/run.py agent

# Terminal 2: MSCAN backend, configured application port (8080 here)
python web_bridge/adapters/mscan/run.py backend

# Terminal 3: MSCAN frontend (8848 in this checkout)
python web_bridge/adapters/mscan/run.py frontend
```

Open `http://YOUR_SERVER_IP:8848/sample/metagenomic`, select a sample, and click
**Ask assistant**. The standalone agent remains at `http://YOUR_SERVER_IP:8000/`.
The helper does not install dependencies, build code or start duplicate servers.
Stop an existing process before starting another on the same port.

The backend helper disables MSCAN's background Cromwell polling for integration
development. Pass `--enable-scheduler` when you intend to enable that existing
MSCAN service. This setting does not disable agent-submitted pipelines.

For different hosts or HTTPS deployment:

```bash
python web_bridge/adapters/mscan/run.py backend \
  --agent-url https://agent.example.com \
  --public-url https://agent.example.com
```

The backend URL must be reachable from Java; the public URL must be reachable
from users' browsers. Configure `AGENT_PUBLIC_ORIGIN`, HTTPS and exact MSCAN
origins as described in [user isolation](../../../docs/user_isolation.md). Do not
embed an HTTP agent in an HTTPS page. CSP `frame-src`/`frame-ancestors` rules at
your proxy must permit the intended hosts.

Without the helper, configure `AGENT_WEBSITE_CLIENTS_FILE` for BioAgent and
`BIOAGENT_ENABLED=true`, `BIOAGENT_URL`, `BIOAGENT_PUBLIC_URL`,
`BIOAGENT_SECRET`, `BIOAGENT_ORIGINS` for MSCAN. The MSCAN service secret must
match its client entry. Never expose it through Vite/browser environment variables.

## Transfer concurrency

`bioagent.transfer-workers` controls the maximum concurrent search, pull and push
commands in one MSCAN backend process; the default is **3**, shared across users.
For example, set `BIOAGENT_TRANSFER_WORKERS=3` in the backend environment before
starting it. This is separate from the agent's conversation/run limit.

The poller reserves a worker slot before leasing a command. Active commands keep
their heartbeat and are excluded from local re-leasing; acknowledgement failures
remain eligible for durable retry. Destination creation is briefly serialized per
owner. Writes to the same sample and receipt are serialized with shared locks;
unrelated samples can transfer concurrently, including alongside automatic
result delivery. These locks coordinate a single MSCAN backend process, not a
multi-instance deployment.

The download menu identifies entries by `resource_id`. Distinct files remain
listed even when their filenames or checksums match; repeated IDs across catalog
pages appear once.

## User identity and production login

The Java controller reads `SecurityUtils.getUserId()` on every call. It never
trusts a user ID submitted by JavaScript. The development login bypass therefore
maps everyone to the configured development user; it does **not** demonstrate
production multi-user separation inside MSCAN. Restore MSCAN's real login before
deployment. Its existing authentication filter protects the controller when the
bypass is off. Check the flow with two real accounts before production release.

New external identities get separate agent accounts. To intentionally share an
existing standalone account, link it before first use:

```bash
export AGENT_WEBSITE_CLIENTS_FILE="$PWD/runtime/website-integration/clients.json"
python -m web_bridge.identity mscan MSCAN_USER_ID AGENT_USERNAME
```

The controller verifies both sample and source-file ownership. Shared-project or
administrator access rules need an explicit host-side permission implementation
if your deployment supports them; this adapter currently accepts the owner only.

The frontend adapter subscribes to the existing Pinia `clearAuth` action before
it clears the token. `WebsiteLogoutHook` observes `TokenService.invalidateSession`
through Spring AOP and publishes the verified identity before invalidation.
Both revoke site-minted agent logins and bridge bindings. The server path does
not depend on browser notification delivery. Neither requires editing MSCAN's
user store or CAS configuration. If the agent
is unreachable, host logout still completes after a bounded request timeout;
MSCAN logs a warning and the remaining agent login expires normally. Existing
standalone agent logins and completed artifacts are retained.

## Validate

Offline HTTP tests cover identity mapping, ownership across users/sites, login
replay/origin checks, resumable transfer, checksums, download tickets, persistent
conversations and scoped logout:

```bash
python -B -m unittest web_bridge.tests.test_integration web_bridge.tests.test_protocol -q
# After packaging MSCAN; requires java and javac on PATH:
python -B -m web_bridge.tests.check_mscan_logout
python -B -m web_bridge.tests.check_mscan_java
# Uses the installed MSCAN frontend dependencies; no live services:
node web_bridge/adapters/mscan/tests/check_sample_files.mjs
```

The opt-in browser acceptance test uses the running MSCAN development bypass and
the existing QC demo sample. It submits paid model requests and downloads test
artifacts. `--pipeline` also runs the tiny bundled `template_wdl` through the
configured remote executor; it does not analyze the sample file.

```bash
python -B -m web_bridge.tests.check_mscan --pipeline
# Optional: exercise unrelated-site embedding in this test browser only.
python -B -m web_bridge.tests.check_mscan \
  --url http://YOUR_SERVER_IP:8848/sample/metagenomic \
  --agent-url http://127.0.0.1:8000 --pipeline
# Check remote completion while the host page is closed:
python -B -m web_bridge.tests.check_mscan --pipeline-only --detach
```

Both MSCAN origins must be configured. Evidence is written under
`runtime/live-validation/mscan-bridge-final/`; credentials are excluded. The
test checks known demo QC values, so adapt that assertion for a different sample.
Real production CAS login is a separate deployment acceptance step.

Page callbacks require a live browser and have a 45-second deadline. They accept
up to 512 KiB per result; use paged tables or backend file transfer for larger
data. Results list the most recent 100 agent runs per conversation. This version
uses polling rather than a webhook delivery service.

## Live validation in this checkout

On 2026-11-03, the running MSCAN frontend/backend, authenticated BioAgent with
Docker workers, GPT-5.6 Sol (Premium), remote Cromwell and object storage were
used together. The browser test placed MSCAN and the assistant on different IP
origins to exercise embedding without cookies.

Verified: automatic mapped sign-in, page tables and QC figures, CSV export,
Markdown report generation, history/artifact restoration after reload, binary
sample import, idempotent repeat import, SHA256-matched downloads from both UIs,
sign-in renewal, real run cancellation, workflow approval, remote WDL completion,
result download back through MSCAN, site-login revocation, and remote workflow
completion while MSCAN was closed. No browser errors
were recorded in the complete acceptance run.

The remote template returned 70 bp, 35.71% GC, and a passing minimum-length check.
One verified Cromwell workflow was `9e53601e-32fc-49d6-a8a2-41e7caac8f64`;
its agent pipeline job was `8fed0e417f6541b79ce0529a002107a3`, with artifacts
available. Pipeline definition files were unchanged.

The offline regression run covered 118 tests (3 skipped), plus the subsequently
added expired-grant/disabled-account check. Agent frontend build, MSCAN Maven
package, MSCAN TypeScript/adapter lint, Docker worker build, architecture smoke
and the standalone browser multitasking check passed.

Local evidence: `runtime/live-validation/mscan-bridge-final/checks.json`,
`template-metrics.json`, `qc-report.txt`, and `integration.png`. The integration
uses MSCAN's development bypass in these checks. The adapter logout hook is also
tested through a real Spring proxy, event context and HTTP receiver. Production CAS sign-in
must still be checked with real accounts when the development bypass is removed.

### Bidirectional analysis

- Navigation and sample/tab changes update the assistant's page context.
- The assistant can list authorized samples/files and import FASTQ, FASTA and
  received analysis files itself. Stale or inaccessible file references are
  omitted; their owned samples remain selectable as destinations.
- Runs started on a selected sample page retain that sample as their delivery
  target. The backend polls for completed outputs even when the page is closed.
- Received files appear under **Download files** on the sample toolbar.
  Registered importers populate native QC, assembly, annotation and other analysis
  records; unknown formats remain downloadable files with an explicit native
  import status. See the [format contracts](../../README.md#analysis-result-exchange).
  The former Agent results panel is removed.
- To transfer standalone results, ask in chat: “Push these results to MSCAN
  project X, sample Y.” The connector can create missing named destinations.
  `website_search` and `website_pull` bring owned sources/results back to the
  agent without a browser tab. There are no dedicated transfer buttons.

Keep `BIOAGENT_RESULTS_ROOT` on persistent MSCAN storage. The default launcher
sets it to `runtime/website-integration/mscan-results`; on another server set an
appropriate absolute path. Include these receipts/files in MSCAN backups. The
poll interval is `bioagent.delivery-poll-ms` (default 5000 ms). Source and result
files remain subject to the existing owner checks; development login bypass is
not a substitute for validating real CAS accounts before production use.

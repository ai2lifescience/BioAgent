# MSCAN integration guide

MSCAN keeps its database, login, storage and workflow service. BioAgent keeps its
accounts, conversations, isolated workers, files and durable run queue. This
integration connects them through the [generic web bridge](../../../docs/web_integration.md).
Other websites implement the same small backend and browser adapter contracts.

## Code organization

BioAgent retains only configuration and reusable validation support here:

```text
mscan/
├── README.md                   # Setup, contracts and validation
└── run.py                      # Development configuration and launch helper
```

Runnable host code is owned only by the sibling repositories:

- `mscan/src/integrations/bioagent/` contains the embedded assistant, page
  context, logout and resource UI.
- `mscan-app/mscan-admin/src/main/java/com/mscan/web/controller/common/`
  contains identity endpoints, transfers, delivery, native importers, resource
  discovery, logout and download security.

`ResultImporterRegistry` owns file-format contracts; `ResultImportService`
handles file-based native import orchestration; `PipelineResultImporter` and
`PipelineResultImporterRegistry` own direct Cromwell pipeline contracts;
`CromwellResultGateway` validates remote workflow state; and
`CromwellResultSyncService` coordinates direct import, ownership, idempotency
and task status. `AssistantDeliveryService` persists verified file receipts;
`AssistantTransferService` handles search/pull/push/result_sync commands; and
`NativeResultResources` exposes owned results. Generic bridge identity and
transfer code stays in BioAgent.

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

## Direct integration

See the [installation guide and exact MSCAN file changes](../../../docs/mscan_web_bridge.md#install-the-web-bridge-in-mscan)
for prerequisites, setup, builds, startup and verification.

The development workspace keeps `BioAgent`, `mscan` and `mscan-app` as sibling
repositories. Host implementation and regression checks are tracked directly
in the two MSCAN repositories. BioAgent does not provide an installer that
writes into them.

```bash
python web_bridge/adapters/mscan/run.py init \
  --origins http://localhost:8848,http://127.0.0.1:8848,http://YOUR_SERVER_IP:8848
npm --prefix frontend run build
docker build -f isolation/deploy/Dockerfile -t bioagent-worker:local .
pnpm --dir ../mscan type:check
mvn -f ../mscan-app/pom.xml clean package -DskipTests
```

Use an actual IP instead of `YOUR_SERVER_IP`. The direct integration changes
three existing host files:
`src/App.vue` mounts the assistant; `src/views/sampleProgramResults/index.vue`
connects selected sample context, result refreshes and the download menu; and
the backend's `application-druid.yml` contains the connector settings. No MSCAN
database migration is required.

Activate the environment providing Java, Maven, Node/pnpm and agent Python first
(for this development checkout, `conda activate openaisdk`). Install each project's
dependencies as usual. `init` creates a private runtime config, retains existing
keys on rerun, enables shared-SSO user IDs and updates the allowed origins.
MSCAN does not read BioAgent runtime files: configure the matching `site-id`,
`secret` and origins directly under `bioagent` in its active
`application-druid.yml`. Treat that YAML as sensitive and restart both services
after changing either side.

## Minimal MSCAN changes

| Existing host files | Bridge changes |
| --- | --- |
| Frontend `src/App.vue` | Import and mount the embedded assistant |
| Frontend `src/views/sampleProgramResults/index.vue` | Sample context, result refresh and download menu |
| Backend `application-druid.yml` | Direct `bioagent.*` connector configuration |
| Frontend `ProgramResultPanel.vue` | Use assembly results for synthetic functional-analysis samples |
| Backend CAS/security/session classes | Unified CAS login and front/back-channel logout |
| Backend DuckDB startup | Normalize inherited HTTP(S) proxy root slashes |

The remaining integration files are additions owned by MSCAN: five
frontend files under `src/integrations/bioagent/` and Java files under the admin
module's `com.mscan.web.controller.common` package. `WebsiteDownloadSecurity`
adds a higher-priority chain scoped only to GET `/assistant/received-download/*`;
the controller still validates the one-use ticket and resource ownership. Other
routes continue through MSCAN's original security chain. Adapter backend beans
are conditional on `bioagent.enabled=true`.

Preserve unrelated host customizations when removing known legacy bridge
insertions. The local `pnpm-workspace.yaml` setting
`packages: ['.']` is separate from the bridge.

## Run

For normal `python -m interfaces.web`, `java -jar` and `pnpm dev` startup, see
[Everyday startup](../../../docs/mscan_web_bridge.md#everyday-startup). BioAgent
reads its private client configuration; MSCAN reads its own active Spring
profile. Direct Java startup preserves MSCAN's normal scheduler settings.

Use three terminals and start each sibling repository directly:

```bash
# BioAgent, port 8000
cd /path/to/mscan_projects/BioAgent && python -B -m interfaces.web --host 0.0.0.0 --port 8000

# MSCAN backend; start.sh also normalizes DuckDB-incompatible proxy URLs
cd /path/to/mscan_projects/mscan-app && ./start.sh start

# MSCAN frontend (8848 in this checkout)
cd /path/to/mscan_projects/mscan && pnpm dev
```

Open `http://YOUR_SERVER_IP:8848/sample/metagenomic`, select a sample, and click
**Ask assistant**. The standalone agent remains at `http://YOUR_SERVER_IP:8000/`.
Stop an existing process before starting another on the same port.

For different hosts or HTTPS deployment, set `bioagent.url` and
`bioagent.public-url` in MSCAN's active profile. The backend URL must be reachable
from Java; the public URL must be reachable
from users' browsers. Configure `AGENT_PUBLIC_ORIGIN`, HTTPS and exact MSCAN
origins as described in [user isolation](../../../docs/user_isolation.md). Do not
embed an HTTP agent in an HTTPS page. CSP `frame-src`/`frame-ancestors` rules at
your proxy must permit the intended hosts.

Configure `AGENT_WEBSITE_CLIENTS_FILE` for BioAgent when its default private
path is not used. MSCAN's service secret must match its client entry. Never
expose it through Vite/browser environment variables.

## Transfer concurrency

`bioagent.transfer-workers` controls the maximum concurrent search, pull, push
and result-sync commands in one MSCAN backend process; the default is **3**,
shared across users.
Set it directly in MSCAN's active Spring profile. This is separate from the
agent's conversation/run limit.

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

## Result contract

MSCAN remains the owner of result persistence and native imports. The connector
leases commands and derives the owner from its authenticated OOS subject;
browser-supplied user IDs are never accepted. A persisted file-push receipt contains only
the schema version, event ID, verified subject, target sample, creation time,
verified file identities and native-import outcome. Session IDs, leases, model
answers and the original command payload are transport-only and are not retained.

Each pipeline output carries a versioned `pipeline_result` reference. Remote WDL
outputs include the real `cromwell_task_id`; local engines omit that field rather
than inventing an ID. This provenance supports the file-import path.

The separate `result_sync` command is metadata-only and supports remote Cromwell
jobs. BioAgent accepts its own pipeline `job_id`, loads the protected broker job
and sends the recorded Cromwell UUID, pipeline key and destination. MSCAN uses a
workflow-derived task-row ID as the idempotency identity and rejects a Cromwell
task already associated with another owner, sample or pipeline. It verifies
remote `Succeeded` status before calling the registered parser. File push remains
available for local-engine outputs and for callers that need artifacts copied.
The current direct registry covers all 23 non-template BioAgent pipelines.
Molecular and risk importers derive the pathogen from Cromwell inputs and resolve
the required `metadata_pathogen_ref`.

For Agent reads, prefer the two backend operations `website_search` and
`website_pull`. Browser callbacks remain for current-page context, visible
tables/figures and navigation; they are not the ownership boundary.

## User identity and production login

The Java controller reads `SecurityUtils.getUserId()` on every call. It never
trusts a user ID submitted by JavaScript. The development login bypass therefore
maps everyone to the configured development user; it does **not** demonstrate
production multi-user separation inside MSCAN. Restore MSCAN's real login before
deployment. Its existing authentication filter protects the controller when the
bypass is off. Check the flow with two real accounts before production release.

`run.py init` configures MSCAN to share its verified SSO user ID with the agent.
On first use the agent creates or reuses the account with that same ID and the
MSCAN username; no manual linking step is required. Existing mappings continue
to resolve to their prior account so an upgrade does not orphan saved work.

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
python -B -m web_bridge.tests.check_mscan_logout \
  --jar ../mscan-app/mscan-admin/target/mscan-admin.jar
python -B -m web_bridge.tests.check_mscan_java --root ../mscan-app
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
- To synchronize a succeeded remote Cromwell result, ask for
  `website_result_sync` with its BioAgent pipeline `job_id`; do not ask to push
  its output files. To transfer standalone/local result files, ask in chat:
  “Push these files to MSCAN project X, sample Y.” The connector can create
  missing named destinations.
  `website_search` and `website_pull` bring owned sources/results back to the
  agent without a browser tab. There are no dedicated transfer buttons.

Keep `bioagent.results-root` on persistent MSCAN storage. The current local
profile uses `./data/agent-results`; production deployments should use an
appropriate persistent absolute path. Include these receipts/files in MSCAN
backups. The poll interval is `bioagent.delivery-poll-ms` (default 5000 ms).
Source and result files remain subject to the existing owner checks; development
login bypass is not a substitute for validating real CAS accounts before
production use.

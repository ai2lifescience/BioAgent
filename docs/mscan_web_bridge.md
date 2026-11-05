# MSCAN web bridge

Use natural-language requests in the agent to find samples, pull data from MSCAN,
and push data and analysis results back to MSCAN.

<a id="main-functions"></a>

## Overview

| Function | Purpose |
| --- | --- |
| **Account linking** | Connect the MSCAN identity to an agent account and enforce access to the user's own data. |
| **Push/pull data and results** | Find and pull authorized files into an agent session; push selected data and results back to MSCAN, creating named projects or samples when requested. |
| **Browser-based page understanding** | Observe the current page, follow navigation and read visible content so the agent understands what the user is viewing. |

Browser understanding combines observation of the rendered page in the connected
MSCAN tab with optional structured context, such as the selected sample and
analysis tab. Data transfers use the backend connection and can continue when
the page is closed.

Already configured? Go to [Everyday startup](#everyday-startup). For a new
installation, complete the setup below first.

<a id="install-the-web-bridge-in-mscan"></a>

## First-time setup

The installer adds adapter-owned files and changes two existing frontend files.
It does not modify existing backend sources or require a database migration.
The [technical reference](#technical-reference) lists the exact changes and checks.

### 1. Prepare the applications

Run the following commands from the **BioAgent repository root**. The default
directory layout is:

```text
resource/mscan/
├── mscan/          # MSCAN Vue frontend
└── mscan-app/      # MSCAN Java backend
```

Have the agent's Python dependencies, Java 17, Maven, Node.js and pnpm available.
Install each frontend's dependencies using its package configuration. MSCAN's
normal database, Redis, object storage and login configuration must already work;
the bridge installer does not provision those services.

In this development environment, activate `openaisdk` first:

```bash
conda activate openaisdk
```

The local `pnpm-workspace.yaml` has an earlier setup fix adding
`packages: ['.']`. If the original frontend reports `packages field missing or
empty`, add that field while retaining its other settings. This package-manager
fix is separate from the web bridge and is not applied by `install.py`.

### 2. Install the adapter

```bash
python web_bridge/adapters/mscan/install.py
```

For a different MSCAN location, pass the directory containing both projects:

```bash
python web_bridge/adapters/mscan/install.py /path/to/mscan-root
```

You do not need to manually edit the two frontend hooks. The installer preserves
line endings, avoids whole-file formatting and can be run repeatedly.

### 3. Configure the connection

Replace `YOUR_SERVER_IP` with the IP address of the server running MSCAN, as
accessed from your browser. For example, if that server is reachable at
`http://192.168.75.56`, use `192.168.75.56` in the command below. With the MSCAN
development frontend on port 8848, the complete browser origin is
`http://192.168.75.56:8848`.

```bash
python web_bridge/adapters/mscan/run.py init \
  --origins http://localhost:8848,http://127.0.0.1:8848,http://YOUR_SERVER_IP:8848
```

This creates `runtime/website-integration/clients.json` with private service
credentials and exact allowed MSCAN origins. Repeating `init` retains the
existing keys and updates the origins. Keep this file private and outside Git.

### 4. Install dependencies and build

From the BioAgent repository root:

```bash
npm --prefix frontend ci
pnpm --dir resource/mscan/mscan install --frozen-lockfile
npm --prefix frontend run build
mvn -f resource/mscan/mscan-app/pom.xml clean package -DskipTests
```

If the agent uses Docker workers, build its worker image as described in
[user isolation](user_isolation.md):

```bash
docker build -f isolation/deploy/Dockerfile -t bioagent-worker:local .
```

For a production MSCAN frontend deployment, also build its static files and
deploy the generated output through your existing hosting setup:

```bash
pnpm --dir resource/mscan/mscan run build:pro
```

The development frontend uses Vite and does not require that production build.

If you want to reuse an existing standalone agent account, complete
[account linking](#account-linking-and-login) before opening the embedded assistant.

## Everyday startup

After [first-time setup](#install-the-web-bridge-in-mscan), use your normal Python,
Java and pnpm commands in three separate terminals. The examples use this
checkout at `/media/data/fuhaoyi/codes/BioAgent` and browser address
`192.168.75.56`; replace these if your deployment differs. Replace the credential
placeholders with your private values. Stop an existing instance before starting
another on the same port.

### Terminal 1 — agent

```bash
conda activate openaisdk
cd /media/data/fuhaoyi/codes/BioAgent

export OPENROUTER_API_KEY="YOUR_OPENROUTER_API_KEY"

export CROMWELL_URL=http://192.168.164.46:39000
export CROMWELL_INPUT_STORAGE_ENDPOINT=http://192.168.164.46:7070
export CROMWELL_INPUT_STORAGE_URI=s3://cncb-web-server-mic/files
export CROMWELL_INPUT_STORAGE_REGION=us-east-1
export CROMWELL_INPUT_STORAGE_MOUNT_PREFIX=/data/versitygw/data/s3
export CROMWELL_INPUT_STORAGE_ACCESS_KEY="YOUR_STORAGE_ACCESS_KEY"
export CROMWELL_INPUT_STORAGE_SECRET_KEY="YOUR_STORAGE_SECRET_KEY"
export CROMWELL_OUTPUT_STORAGE_URI=s3://cncb-web-server-mic/cromwell/outputs
export CROMWELL_OUTPUT_STORAGE_MOUNT_PREFIX=/data/versitygw/data/s3/cncb-web-server-mic/cromwell/outputs
export CROMWELL_OUTPUT_STORAGE_EXECUTION_PATH_PREFIXES=/data/zhaomh/cromwell-workspace/cromwell-executions,/cromwell-share/cloud_cromwell/cromwell-executions

export AGENT_PROXY=socks5h://127.0.0.1:10801

unset AGENT_WEBSITE_CLIENTS
export AGENT_WEBSITE_CLIENTS_FILE="$PWD/runtime/website-integration/clients.json"

python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

### Terminal 2 — MSCAN backend

```bash
conda activate openaisdk
cd /media/data/fuhaoyi/codes/BioAgent

export BIOAGENT_ENABLED=true
export BIOAGENT_URL=http://127.0.0.1:8000
export BIOAGENT_PUBLIC_URL=http://192.168.75.56:8000
export BIOAGENT_ORIGINS=http://localhost:8848,http://127.0.0.1:8848,http://192.168.75.56:8848
export BIOAGENT_RESULTS_ROOT="$PWD/runtime/website-integration/mscan-results"

export BIOAGENT_SECRET="$(python -c 'import json; print(json.load(open("runtime/website-integration/clients.json"))["mscan"]["secret"])')"

cd resource/mscan/mscan-app

mvn clean package -DskipTests &&
java -jar mscan-admin/target/mscan-admin.jar \
  --spring.profiles.active=druid
```

### Terminal 3 — MSCAN frontend

```bash
conda activate openaisdk
cd /media/data/fuhaoyi/codes/BioAgent/resource/mscan/mscan

pnpm install --frozen-lockfile &&
pnpm dev
```

Open `http://192.168.75.56:8000` for the standalone agent or
`http://192.168.75.56:8848` for MSCAN. Sign in using your configured MSCAN login,
select a sample and open **Ask assistant**. Local MSCAN access can use
`http://localhost:8848`. Its browser origin must be allowed in both
`BIOAGENT_ORIGINS` and the agent's private client configuration.

The agent reads `runtime/website-integration/clients.json`; the backend export
loads the matching service credential from that same file before changing
directories. If reading it fails, stop and complete connection configuration
before starting Java. These exports enable the bridge without a startup helper.

You do **not** need Maven or `pnpm install` for every restart. Rebuild the backend
after code changes; install dependencies after their declarations or lockfiles
change. Keep real API and storage keys in your private environment, outside Git.

## Account linking and login

The service credential identifies **MSCAN's backend** to the agent. MSCAN's
user login identifies **the person**. `run.py init` generates the service and
signing secrets; it does not know or store a user's login password.

The agent maps `(site_id, MSCAN user ID)` to an agent account. On first use, an
unlinked MSCAN identity gets a separate agent account. Usernames and email
addresses are not automatically matched. To use an existing agent account, an
administrator can link it **before the first connection**:

```bash
# Run from the BioAgent root, with the same configuration/database as the server.
unset AGENT_WEBSITE_CLIENTS
export AGENT_WEBSITE_CLIENTS_FILE="$PWD/runtime/website-integration/clients.json"
python -m web_bridge.identity mscan MSCAN_USER_ID AGENT_USERNAME
```

Use MSCAN's actual internal user ID, not an assumed display name. Reassigning an
identity already linked to another agent account is rejected. Account mappings
are stored in the authentication database, not in `clients.json`.

The development login bypass supplies a configured development user without a
login screen. Restore real MSCAN login for distinct users; the adapter reads the
verified user from MSCAN's backend authentication. Production CAS sign-in still
needs acceptance testing with real accounts; development bypass checks do not
establish production user separation.

MSCAN logout revokes that site's agent logins and bridge bindings while retaining
completed artifacts, standalone agent logins and the persistent identity mapping.
Logout is not permanent unlinking; there is currently no public unlink endpoint
or unlink CLI. See [identity and production login](../web_bridge/adapters/mscan/README.md#user-identity-and-production-login)
for the adapter's ownership rules and logout behavior.

<a id="example-requests"></a>

## Usage examples

> “Find my samples in MSCAN project A.”

> “Pull the FASTQ files for sample B and run QC.”

> “Push these results to sample B in MSCAN.”

> “Create project C, add this sample, and upload its data and results.”

Search, pull and push use natural language in the agent; no transfer buttons are
needed on the agent page. Backend transfers require a linked identity and a
running connector, but can continue with the browser closed. Page observation
requires the connected MSCAN tab.

Received files appear in **Download files** on the sample toolbar. Supported
result formats also populate native MSCAN analysis records. Check `file_delivery`
and each job's `native_imports` separately: receiving a ZIP does not prove that
native records were imported. An unsupported or incomplete format can remain a
downloadable file. See the [supported importer contracts](../web_bridge/README.md#analysis-result-exchange).

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| **Ask assistant** is missing | Start the backend with `BIOAGENT_ENABLED=true` and the matching service credential. Confirm the agent is running and reachable at `BIOAGENT_PUBLIC_URL`; reload MSCAN. |
| Origin is rejected | Match the browser's exact scheme, hostname and port in `clients.json` and `BIOAGENT_ORIGINS`. Check any explicit `AGENT_WEBSITE_SITES` override. Restart affected services after changes. |
| Connection or sign-in fails | Confirm both processes use the same MSCAN service secret and that MSCAN has an authenticated user (or the development bypass). Java uses `BIOAGENT_URL`; browsers use `BIOAGENT_PUBLIC_URL`. |
| `clients.json` cannot be read | Run `run.py init` for first-time setup or correct the file path. Run the backend credential export from the BioAgent root, before `cd resource/mscan/mscan-app`. |
| Transfer remains queued/running | Check `website_transfer_status` and the MSCAN backend logs. The backend connector must remain running. A queued response is not a completed transfer. |
| Files arrived but native results are missing | Inspect `native_imports` for missing output roles, incompatible sample types, unsupported formats or parser errors. Resolve the reported cause before retrying a failed transfer. |
| Native results exist but the page is stale | Reload the selected sample/view. Automatic refresh can miss status-only receipt updates; verify the import receipt before assuming a transfer failed. |

For agent login, Docker workers and storage limits, see [user isolation](user_isolation.md).
For generic API, origin and transfer contracts, see [web integration](web_integration.md).

## Updates and custom deployments

### After code or configuration changes

| Change | Required action |
| --- | --- |
| MSCAN adapter source | Rerun `install.py`, rebuild the affected frontend/backend and restart it. Installed copies under `resource/mscan/` are replaced by the installer. |
| Agent frontend or embed SDK | Run `npm --prefix frontend run build`, then reload the browser. |
| Agent Python code | Restart the agent; rebuild its worker image when worker/tool code changes. |
| Dependencies or lockfiles | Reinstall the affected dependencies and rebuild that application/image. |
| Private client origins or service credentials | Keep agent and MSCAN settings consistent, re-export values and restart affected services. Rerunning `init` preserves existing secrets and updates origins. |

Keep the existing private configuration and account databases across restarts.
You do not need to rerun `init` or relink users for ordinary restarts.

### Custom configuration and optional launcher

For normal startup, use the [three terminals above](#everyday-startup).
`run.py` remains an optional alternative that loads configuration and starts each
process for you. Do not run both methods on the same ports:

```bash
# Terminal 1: agent (port 8000)
python web_bridge/adapters/mscan/run.py agent

# Terminal 2: MSCAN backend (its configured port, 8080 in this checkout)
python web_bridge/adapters/mscan/run.py backend

# Terminal 3: MSCAN development frontend (8848 in this checkout)
python web_bridge/adapters/mscan/run.py frontend
```

With direct commands, select an alternative private config by exporting
`AGENT_WEBSITE_CLIENTS_FILE=/absolute/path/to/clients.json` in the agent terminal
and using that same file in the backend's `BIOAGENT_SECRET` command. Clear an
inline `AGENT_WEBSITE_CLIENTS` override as shown above. If you explicitly set
`AGENT_WEBSITE_SITES`, keep it consistent with the configured browser origins.
For separate hosts, set `BIOAGENT_URL` to an address reachable by Java and
`BIOAGENT_PUBLIC_URL` to an address reachable by users' browsers.
`BIOAGENT_RESULTS_ROOT` selects persistent result storage. Direct Java startup
keeps MSCAN's normal scheduler configuration;
append `--scheduled.cromwellPoll.enabled=false` only when you want polling disabled.

For a non-default checkout, add `--mscan-root /path/to/mscan-root` to the
optional backend/frontend launcher commands. For separate hosts with the launcher,
set both agent addresses:

```bash
python web_bridge/adapters/mscan/run.py backend \
  --agent-url https://agent.example.com \
  --public-url https://agent.example.com
```

`--agent-url` must be reachable from Java; `--public-url` must be reachable from
users' browsers. The backend launcher disables MSCAN's background workflow
poller for integration development; add `--enable-scheduler` when that MSCAN
service should run. Agent pipeline execution is configured separately.

MSCAN processes up to three bridge transfer commands concurrently by default. Set `BIOAGENT_TRANSFER_WORKERS`
in the backend environment to change that limit; writes to the same sample remain
serialized within that backend process.

## Technical reference

Embedded chat, native result importers, result refreshes and logout synchronization
support these three functions. The generic web bridge handles identity,
communication, browser observation and transfers; the MSCAN adapter supplies
MSCAN-specific project, sample and result mappings. Agent-facing tool definitions
live in `tools/function_tools/website/`; the website specialist lives in
`tools/agent_tools/specialist/website_guide.py`. Other modules can call bridge
services directly without the agent tool layer.

### Flow chart

```mermaid
flowchart TD
    User[User] --> Login

    subgraph Identity["1. Account linking"]
        Login[MSCAN login] --> Link[Map MSCAN identity to agent account]
        Link --> Access[Linked identity and ownership checks]
    end

    User -->|Natural-language request| Agent[Agent]
    Access -->|Authorize linked access| Agent

    subgraph Browser["3. Browser-based page understanding"]
        Page[Current MSCAN page] --> Observe[Observe visible content and navigation]
        Observe --> Context[Page snapshot and optional sample context]
    end
    Context -->|Inform the response or action| Agent

    Agent -->|Search, pull or push request| Check
    Access --> Check
    subgraph Transfer["2. Push/pull data and results"]
        Check[Validate ownership and transfer scope] --> Action{Requested operation}
        Action -->|Search or pull| Find[Find authorized MSCAN samples and files]
        Find --> Pull[Pull selected files into the agent session]
        Action -->|Push| Target[Resolve destination project and sample]
        Target -->|Create missing destinations when requested| Upload[Transfer selected agent data and results]
        Upload --> Import[Import supported native records; retain other files for download]
    end

    Find -->|Search results| Agent
    Pull -->|Files available for analysis| Agent
    Import -->|Delivery and import status| Agent
    Import -->|Refresh when the page is open| Page
    Agent -->|Answer and results| User
```

### Installation baseline

The installation procedure was checked against the original `resource/mscan.zip`
and `resource/mscan-app.zip`. A different MSCAN version may need its frontend
hooks adapted. Maintain integration sources in `web_bridge/adapters/mscan/`.

### Existing MSCAN files changed

Paths in this table are relative to the MSCAN frontend, `resource/mscan/mscan/`.

| File | What the installer adds | Purpose |
| --- | --- | --- |
| `src/App.vue` | `AssistantBridge` import and component | Mount the embedded assistant across page navigation |
| `src/views/sampleProgramResults/index.vue` | Context registration, result-refresh listener, component refresh key and `SampleFileMenu` | Share the selected sample and tab, refresh received results and provide downloads |

MSCAN's existing backend Java files, database services, pipeline definitions,
`SecurityConfig.java`, `CasClientConfig.java`, frontend user store and QC panel
remain unchanged on a clean installation.

### New adapter files installed

| Destination | Added files |
| --- | --- |
| Frontend `src/integrations/bioagent/` | `AssistantBridge.vue`, `context.ts`, `logout.ts`, `SampleFileMenu.vue`, `sampleFiles.ts` |
| Backend `mscan-admin/src/main/java/com/mscan/web/controller/common/` | `AssistantController.java`, `AssistantTransferService.java`, `AssistantDeliveryService.java`, `TransferLocks.java`, `ResultImporterRegistry.java`, `ResultImportService.java`, `QcResultImporter.java`, `NativeImportContext.java`, `NativeResultResources.java`, `WebsiteLogoutEvent.java`, `WebsiteLogoutHook.java`, `WebsiteDownloadSecurity.java` |

Logout uses a frontend Pinia action subscription and a backend Spring aspect
that observes the verified session before invalidation. Download security uses
an added filter chain scoped to GET `/assistant/received-download/*`; the
controller validates the expiring, one-use ticket and resource ownership.
Other routes retain MSCAN's existing authentication.

On upgrades from older bridge installations, the installer removes its exact
legacy edits from the user store, CAS configuration and security configuration,
as well as renamed adapter classes and their stale compiled output. It preserves
unrelated host customizations.

### Verify installation

With the original ZIPs present, check installation in a temporary clean copy:

```bash
python -B -m web_bridge.tests.check_mscan_install
```

This compares original files byte for byte, verifies that only the two frontend
files change, and checks repeat installation. It does not modify the running
checkout. After building MSCAN, run the adapter checks:

```bash
python -B -m web_bridge.tests.check_mscan_java
python -B -m web_bridge.tests.check_mscan_logout
node web_bridge/adapters/mscan/tests/check_sample_files.mjs
```

These cover native resource ownership, result importing, QC formats, scoped
download security, bounded transfer concurrency, same-name file downloads and logout revocation. They do not run analysis pipelines.
For browser acceptance checks and their requirements, see
[Validate](../web_bridge/adapters/mscan/README.md#validate).

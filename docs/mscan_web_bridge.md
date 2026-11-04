# MSCAN web bridge

Use natural-language requests in the agent to find samples, pull data from MSCAN,
and push data and analysis results back to MSCAN.

## Main functions

| Function | Purpose |
| --- | --- |
| **Account linking** | Connect the MSCAN identity to an agent account and enforce access to the user's own data. |
| **Push/pull data and results** | Find and pull authorized files into an agent session; push selected data and results back to MSCAN, creating named projects or samples when requested. |
| **Browser-based page understanding** | Observe the current page, follow navigation and read visible content so the agent understands what the user is viewing. |

Browser understanding combines observation of the rendered page in the connected
MSCAN tab with optional structured context, such as the selected sample and
analysis tab. Data transfers use the backend connection and can continue when
the page is closed.

Embedded chat, native result importers, result refreshes and logout synchronization
support these three functions. The generic web bridge handles identity,
communication, browser observation and transfers; the MSCAN adapter supplies
MSCAN-specific project, sample and result mappings. Agent-facing tool definitions
live in `tools/function_tools/website/`; the website specialist lives in
`tools/agent_tools/specialist/website_guide.py`. Other modules can call bridge
services directly without the agent tool layer.

## Flow chart

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

## Example requests

> “Find my samples in MSCAN project A.”

> “Pull the FASTQ files for sample B and run QC.”

> “Push these results to sample B in MSCAN.”

> “Create project C, add this sample, and upload its data and results.”

## Install the web bridge in MSCAN

The installer adds the MSCAN adapter and modifies **two existing frontend files**.
It does not modify existing backend source files or require a database migration.
Installation must be followed by connection configuration, builds and service
restarts.

This procedure was checked against the original `resource/mscan.zip` and
`resource/mscan-app.zip`. A different MSCAN version may need its frontend hooks
adapted. Maintain integration code in `web_bridge/adapters/mscan/`; installed
copies under `resource/mscan/` are replaced when the installer runs again.

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

#### Existing MSCAN files changed

Paths in this table are relative to the MSCAN frontend, `resource/mscan/mscan/`.

| File | What the installer adds | Purpose |
| --- | --- | --- |
| `src/App.vue` | `AssistantBridge` import and component | Mount the embedded assistant across page navigation |
| `src/views/sampleProgramResults/index.vue` | Context registration, result-refresh listener, component refresh key and `SampleFileMenu` | Share the selected sample and tab, refresh received results and provide downloads |

MSCAN's existing backend Java files, database services, pipeline definitions,
`SecurityConfig.java`, `CasClientConfig.java`, frontend user store and QC panel
remain unchanged on a clean installation.

#### New adapter files installed

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

### 3. Configure the connection

Replace `YOUR_SERVER_IP` with the address used in your browser:

```bash
python web_bridge/adapters/mscan/run.py init \
  --origins http://localhost:8848,http://127.0.0.1:8848,http://YOUR_SERVER_IP:8848
```

This creates `runtime/website-integration/clients.json` with private service
credentials and exact allowed MSCAN origins. Repeating `init` retains the
existing keys and updates the origins. Keep this file private and outside Git.

The launcher reads this configuration for both applications. Keep the agent's
existing model, workflow executor and storage environment variables in its
terminal. For account linking and production login, see
[User identity and production login](../web_bridge/adapters/mscan/README.md#user-identity-and-production-login).
The development login bypass maps visitors to the development user; restore
MSCAN's normal login for deployment with distinct users.

### 4. Build

After installing dependencies:

```bash
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

The development frontend launcher below uses Vite and does not require that
production build.

### 5. Start or restart

Stop existing instances before starting replacements on the same ports. Use
three terminals, each starting from the BioAgent repository root:

```bash
# Terminal 1: agent (port 8000)
python web_bridge/adapters/mscan/run.py agent

# Terminal 2: MSCAN backend (its configured port, 8080 in this checkout)
python web_bridge/adapters/mscan/run.py backend

# Terminal 3: MSCAN development frontend (8848 in this checkout)
python web_bridge/adapters/mscan/run.py frontend
```

For a non-default checkout, add `--mscan-root /path/to/mscan-root` to the
backend and frontend commands. For separate hosts, set both agent addresses:

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

Open `http://YOUR_SERVER_IP:8848/sample/metagenomic`, select a sample and open
**Ask assistant**. Push and pull use natural-language requests. Received files
appear in the sample's download menu; supported result formats populate native
MSCAN records. See the [supported importer contracts](../web_bridge/README.md#analysis-result-exchange).

### 6. Verify installation

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

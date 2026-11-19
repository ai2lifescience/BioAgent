# MSCAN web bridge

Use BioAgent inside MSCAN to find samples, move files and synchronize completed
Cromwell results.

<a id="main-functions"></a>

## Overview

| Function | Purpose |
| --- | --- |
| **Unified identity** | Reuse the authenticated MSCAN SSO user ID in the agent and enforce access to the user's own data. |
| **Files and results** | Pull authorized files into an agent session, push files to a sample, or ask MSCAN to import a completed Cromwell result. |
| **Page context** | Read the visible MSCAN page, including the selected sample and analysis tab. |

Page observation requires an open MSCAN tab. Backend transfers can continue
after the tab closes.

Already configured? Go to [Everyday startup](#everyday-startup). For a new
installation, complete the setup below first.

<a id="install-the-web-bridge-in-mscan"></a>

## First-time setup

### 1. Prepare the applications

Use the `mscan_agent_dev` branch in both MSCAN repositories for the embedded
assistant and the Cromwell `result_sync` connector. In this workspace the
checkouts are under `resource/mscan/`:

```text
BioAgent/
└── resource/mscan/
    ├── mscan/      # MSCAN Vue frontend
    ├── mscan-app/  # MSCAN Java backend
    └── oauth/      # CNCB OAuth broker, develop branch
```

In each MSCAN checkout, switch branches after saving any local changes:

```bash
git -C resource/mscan/mscan switch mscan_agent_dev
git -C resource/mscan/mscan-app switch mscan_agent_dev
```

Use the `openaisdk` environment with the BioAgent Python dependencies, Java 17,
Maven, Node.js and pnpm. MSCAN also needs its database, Redis and object storage.

### 2. Configure the connection

The OAuth example below uses `localhost`. Include the exact MSCAN origin users
open in their browser when configuring the connector.

```bash
conda activate openaisdk
python web_bridge/adapters/mscan/run.py init \
  --origins http://localhost:8848,http://127.0.0.1:8848,http://192.168.75.56:8848
```

This configures BioAgent's private
`runtime/website-integration/clients.json`, including the service/signing
credentials, exact allowed MSCAN origins and shared-SSO identity mode.

The MSCAN backend derives its BioAgent service URL and browser URL from the
`BIOAGENT_PORT` exported in Terminal 2. Match the site ID, secret, and allowed
origins to the BioAgent client entry only when overriding their defaults; keep
real credentials in private configuration.

In the same active Spring profile, configure MSCAN's `oauth.server-url`,
`oauth.client-secret`, `oauth.redirect-uri` and `oauth.post-logout-redirect-uri`
to match its broker registration. The development callback uses
`/cncb/oauth/callback` on the MSCAN backend and follows `MSCAN_PORT`.

### 3. Install dependencies and build

If pnpm reports `packages field missing or empty`, add `packages: ['.']` at the
top level of `resource/mscan/mscan/pnpm-workspace.yaml` and keep its existing
`allowBuilds` settings. Then run these commands from the BioAgent root:

```bash
npm --prefix frontend ci
pnpm --dir resource/mscan/mscan install --frozen-lockfile
npm --prefix frontend run build
mvn -f resource/mscan/mscan-app/pom.xml clean package -DskipTests
```

For LAN deployments, build the agent's Docker worker image as described in
[user isolation](user_isolation.md):

```bash
docker build -f isolation/deploy/Dockerfile -t bioagent-worker:local .
```

For a production MSCAN frontend deployment, also build its static files and
deploy the generated output through your existing hosting setup:

```bash
pnpm --dir resource/mscan/mscan run build:pro
```

## Everyday startup

The MSCAN frontend uses `8848`. BioAgent and the OAuth broker automatically
load their repository-root `.env` files for stable, non-secret settings. The
files are ignored by Git. Explicit `export` values take precedence over `.env`.

Only ports and secrets need to be exported before starting a service. To move a
service, change only `BIOAGENT_PORT`, `MSCAN_PORT`, or `OAUTH_PORT`; BioAgent,
the OAuth broker, MSCAN, and the Vite proxy derive their dependent local URLs
from those values. Export only the settings listed in the terminal where that
service starts.

After [first-time setup](#install-the-web-bridge-in-mscan), run each application
in a separate terminal. Paths are relative to the BioAgent repository root.
Stop the MSCAN backend before rebuilding its JAR or starting another instance
on the same port.

### Terminal 0 — CNCB OAuth service

Follow `resource/mscan/oauth/README.md` to create the `cncb-oauth` environment
and configure the broker. Register its public `/cas/callback` with CNCB CAS,
then register each application's exact callback and logout URLs in the broker.
Use a separate client secret for BioAgent and MSCAN. Before starting the
broker, its repository-root `.env` is loaded automatically. Export only
its ports, database URL, and client secrets:

```bash
cd resource/mscan/oauth
conda activate cncb-oauth

# OAuth derives registered callback URLs from all three ports.
export BIOAGENT_PORT=8008
export MSCAN_PORT=8080
export OAUTH_PORT=8090
export BIOAGENT_OAUTH_CLIENT_SECRET="REPLACE_BIOAGENT_OAUTH_CLIENT_SECRET"
export OAUTH_MSCAN_CLIENT_SECRET="REPLACE_WITH_THE_MSCAN_OAUTH_CLIENT_SECRET"
export OAUTH_DB="mysql://REPLACE_DB_USER:REPLACE_DB_PASSWORD@REPLACE_DB_HOST:3306/cncb_oauth?charset=utf8mb4"
```

The OAuth `.env` supplies its bind host, public host, and CAS endpoints.

Optional: require CNCB sign-in even if the supplied development configuration
enables the bypass.

```bash
export OAUTH_AGENT_LOGIN_BYPASS=false
```

Start the broker:

```bash
python -m oauth_service.server
```

### Terminal 1 — BioAgent

#### Runtime and MSCAN connector

Before starting BioAgent, its repository-root `.env` is loaded automatically.
Export only `BIOAGENT_PORT`, `OAUTH_PORT`, and the model, OAuth, and storage
secrets:

```bash
conda activate openaisdk

export BIOAGENT_PORT=8008
export OAUTH_PORT=8090
export OPENROUTER_API_KEY="YOUR_OPENROUTER_API_KEY"
export CROMWELL_INPUT_STORAGE_ACCESS_KEY="YOUR_STORAGE_ACCESS_KEY"
export CROMWELL_INPUT_STORAGE_SECRET_KEY="YOUR_STORAGE_SECRET_KEY"
export BIOAGENT_OAUTH_CLIENT_SECRET="REPLACE_BIOAGENT_OAUTH_CLIENT_SECRET"
```

The `.env` file contains the stable proxy, Cromwell endpoint and path settings.

#### Authentication

Choose OAuth or CAS for BioAgent SSO. The MSCAN backend uses its own OAuth
client configuration. For standalone access without SSO, see
[BioAgent web usage](web_usage.md#proxy-and-lan-access).

##### Shared CNCB OAuth with MSCAN

Use this mode when the browser, BioAgent, MSCAN and the OAuth broker run on the
same machine and both apps sign in through the shared CNCB broker.

The required BioAgent settings are listed under Terminal 1; MSCAN's listener
and OAuth client settings are listed under Terminal 2.

#### Start BioAgent

Start BioAgent for the localhost OAuth example:

```bash
python -B -m interfaces.web --host "$BIOAGENT_BIND_HOST" --port "$BIOAGENT_PORT"
```

### Terminal 2 — MSCAN backend

```bash
conda activate openaisdk
cd resource/mscan/mscan-app

export BIOAGENT_PORT=8008  # Must match Terminal 1.
export MSCAN_PORT=8080
export OAUTH_PORT=8090     # Must match Terminal 0.
export OAUTH_MSCAN_CLIENT_SECRET="REPLACE_WITH_THE_MSCAN_OAUTH_CLIENT_SECRET"

java -jar mscan-admin/target/mscan-admin.jar \
  --spring.profiles.active=druid
```

Rebuild the JAR if you change backend code or configuration packaged in it.

### Terminal 3 — MSCAN frontend

```bash
conda activate openaisdk
cd resource/mscan/mscan

pnpm --ignore-workspace run dev
```

Open MSCAN at `http://localhost:8848`, sign in, select a sample and open
**Ask assistant**. Enable that origin in both applications.

## Unified identity and login

The bridge secret authenticates MSCAN's backend. MSCAN sends the verified SSO
user ID and username, which BioAgent uses to open the embedded account. In
standalone `oauth` or `cas` mode, the same verified CNCB user ID opens that same
account. Existing explicit account links take precedence.

Connector logout revokes embedded grants and bindings while preserving
conversation history, files and account links. See
[identity and production login](../web_bridge/adapters/mscan/README.md#user-identity-and-production-login)
for the ownership and logout rules.

<a id="example-requests"></a>

## Usage examples

> “Find my samples in MSCAN project A.”

> “Pull the files for sample B into my workspace.”

> “Synchronize the completed BioAgent pipeline job `<job_id>` to MSCAN project A,
> sample B.”

> “Upload these files to sample B in project C. Create the destination if it is missing.”

Use the **BioAgent pipeline job ID** with `website_result_sync`. BioAgent uses
it to look up the completed job in the current session and sends the recorded
Cromwell task ID and pipeline key to MSCAN. MSCAN retrieves the result from
Cromwell and reports `state: imported` when it finishes. This path produces no
file receipt.

Use `website_push` to copy files. They appear in **Download files** on the
sample toolbar. Check `file_delivery` for delivery and `native_imports` for any
native records MSCAN was able to create. See the
[importer contracts](../web_bridge/README.md#analysis-result-exchange).

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| **Ask assistant** is missing | Set `bioagent.enabled: true` in MSCAN's active profile. Confirm the agent is running and reachable at `bioagent.public-url` (or the derived browser-host URL), then reload MSCAN. |
| MSCAN origin is rejected | Match the browser's exact scheme, hostname and port in BioAgent's client config and MSCAN's `bioagent.origins`. Check any explicit `AGENT_WEBSITE_SITES` override. |
| BioAgent rejects the request host | For SSO, check that the browser is using the host and port in `AGENT_PUBLIC_ORIGIN`. For direct LAN password login, see [Multi-user access](web_usage.md#multi-user-access). |
| Embedded sign-in fails | Confirm the site ID and bridge secret match and that the MSCAN user is signed in. Java uses `bioagent.url`, while browsers use `bioagent.public-url`. |
| BioAgent cannot read `clients.json` | Run `run.py init` from the BioAgent root or correct `AGENT_WEBSITE_CLIENTS_FILE`. |
| Transfer stays queued or running | Check `website_transfer_status` and the MSCAN backend logs. Confirm the connector is running. |
| `No such job in this session` | Use the BioAgent pipeline job ID in the conversation that owns it. |
| Need the final transfer details | Call `website_transfer_status(transfer_id)`. File-push receipts are also saved under `bioagent.results-root` as `<transfer-id>/receipt.json`. |
| Files arrived but native results are missing | Inspect `native_imports` for missing output roles, incompatible sample types, unsupported formats or parser errors. Resolve the reported cause before retrying a failed transfer. |
| Native results exist but the page is stale | Reload the selected sample or result view after confirming the import status. |

For agent login, Docker workers and storage limits, see [user isolation](user_isolation.md).
For generic API, origin and transfer contracts, see [web integration](web_integration.md).

## After code or configuration changes

| Change | Required action |
| --- | --- |
| MSCAN adapter source | Apply the change directly in the tracked `mscan` or `mscan-app` integration files, rebuild the affected project and restart it. |
| Agent frontend or embed SDK | Run `npm --prefix frontend run build`, then reload the browser. |
| Agent Python code | Restart BioAgent. Rebuild the Docker worker image when worker or tool code changes. |
| Dependencies or lockfiles | Reinstall the affected dependencies and rebuild that application/image. |
| Client origins, URLs or service credentials | Update both configurations. Rebuild the MSCAN JAR if it contains the changed settings, then restart both services. |

Keep the private configuration and account databases across restarts. Rerun
`init` when the set of allowed MSCAN origins changes. It preserves existing
service and signing secrets.

## Technical reference

BioAgent's generic bridge handles identity, page context and transfer commands.
MSCAN owns the mapping to projects and samples, file receipts and native result
imports. The agent tools live under `tools/function_tools/website/`.

### Flow chart

```mermaid
flowchart TD
    Login[MSCAN login] --> Account[Verified BioAgent account]
    Page[Open MSCAN page] -->|Page context| Agent[BioAgent conversation]
    Account --> Agent
    Agent --> Connector[MSCAN connector checks ownership]
    Connector -->|Search or pull| Workspace[Find files or copy them to the workspace]
    Connector -->|File push| Files[Attach files to an MSCAN sample]
    Connector -->|Result sync| Cromwell[Read the completed result from Cromwell]
    Cromwell --> Import[Import native MSCAN records]
    Files --> Status[Transfer status]
    Import --> Status
```

### MSCAN integration paths

Paths below are relative to `resource/mscan/`.

| Path | Role |
| --- | --- |
| `mscan/src/App.vue` | Mounts the embedded assistant. |
| `mscan/src/integrations/bioagent/` | Embedded assistant, sample context, logout and downloads. |
| `mscan/src/views/sampleProgramResults/index.vue` | Shares the selected sample and tab and refreshes results. |
| `mscan-app/mscan-admin/src/main/java/com/mscan/web/controller/common/` | Connector endpoints, transfer workers, file receipts and Cromwell result import. |
| `mscan-app/mscan-admin/src/main/resources/application-druid.yml` | Development connector and OAuth settings. |

### Verify the direct integration

Build the directly integrated projects and run the adapter checks:

```bash
pnpm --dir resource/mscan/mscan type:check
mvn -f resource/mscan/mscan-app/pom.xml clean package -DskipTests
python -B -m web_bridge.tests.check_mscan_java --root resource/mscan/mscan-app
python -B -m web_bridge.tests.check_mscan_logout \
  --mscan-root resource/mscan/mscan-app
```

These cover frontend typing, backend compilation, native resource ownership,
result importing, QC formats, scoped download security, bounded transfer
concurrency and logout revocation. They do not run analysis pipelines.
For browser acceptance checks and their requirements, see
[Validate](../web_bridge/adapters/mscan/README.md#validate).

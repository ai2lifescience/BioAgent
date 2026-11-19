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

Already configured? Go to [Everyday startup](#everyday-startup).

<a id="install-the-web-bridge-in-mscan"></a>

## First-time setup

### 1. Prepare the applications

Keep the three checkouts under `resource/mscan/`. After saving local changes,
switch to the integration branches from the BioAgent root.

```bash
git -C resource/mscan/mscan switch mscan_agent_dev
git -C resource/mscan/mscan-app switch mscan_agent_dev
git -C resource/mscan/oauth switch develop
```

Use the `openaisdk` environment with the BioAgent Python dependencies, Java 17,
Maven, Node.js and pnpm. MSCAN also needs its database, Redis and object storage.

### 2. Configure the connection

```bash
conda activate openaisdk
python web_bridge/adapters/mscan/run.py init
```

`init` writes `runtime/website-integration/clients.json`, configures shared
SSO, and allows MSCAN at `http://localhost:8848` and `http://127.0.0.1:8848`.
To use other origins, pass the full comma-separated list to `init --origins`
and set `BIOAGENT_ORIGINS` in the MSCAN backend to match. Rerunning `init`
preserves the existing service and signing secrets.

Terminal 2 loads `BIOAGENT_SECRET` from the `mscan.secret` value in that file.
Use the same `OAUTH_MSCAN_CLIENT_SECRET` in Terminals 0 and 2.

### 3. Install dependencies and build

Run these commands from the BioAgent root.

```bash
npm --prefix frontend ci
pnpm --dir resource/mscan/mscan --ignore-workspace install --frozen-lockfile
npm --prefix frontend run build
mvn -f resource/mscan/mscan-app/pom.xml clean package -DskipTests
```

If you use isolated workers, [build the worker image](user_isolation.md#build-the-worker-image).

For a production MSCAN frontend build, run the following command.

```bash
pnpm --dir resource/mscan/mscan --ignore-workspace run build:pro
```

## Everyday startup

BioAgent uses port `8000`. The broker uses `8090`, the MSCAN backend uses
`8080`, and the MSCAN frontend uses `8848`.

After [first-time setup](#install-the-web-bridge-in-mscan), start each block in
a separate terminal from the BioAgent root.
Replace the credential placeholders with your private values. For BioAgent
and the broker, shell exports take precedence over values in `.env` files.

### Terminal 0 — CNCB OAuth service

Use `resource/mscan/oauth/README.md` to create the `cncb-oauth` environment
and register the broker's public `/cas/callback` with CNCB CAS. Use separate
client secrets for BioAgent and MSCAN. URL-encode the database password in
`OAUTH_DB`.

```bash
cd resource/mscan/oauth
conda activate cncb-oauth

export BIOAGENT_PORT=8000
export OAUTH_BIND_HOST=0.0.0.0

export BIOAGENT_OAUTH_CLIENT_SECRET="YOUR_BIOAGENT_OAUTH_SECRET"
export OAUTH_MSCAN_CLIENT_SECRET="YOUR_MSCAN_OAUTH_SECRET"
export OAUTH_DB="mysql://YOUR_DB_USER:YOUR_DB_PASSWORD@YOUR_DB_HOST:3306/cncb_oauth?charset=utf8mb4"

export CNCB_CAS_LOGIN_URL=https://sso.cncb.ac.cn/login
export CNCB_CAS_VALIDATE_URL=https://sso.cncb.ac.cn/serviceValidate
export CNCB_CAS_LOGOUT_URL=https://sso.cncb.ac.cn/logout
export OAUTH_FLEXIBLE_REDIRECTS=true
export OAUTH_AGENT_LOGIN_BYPASS=false

python -m oauth_service.server
```

### Terminal 1 — BioAgent

Use the same `BIOAGENT_OAUTH_CLIENT_SECRET` as Terminal 0.

```bash
conda activate openaisdk

export OPENROUTER_API_KEY="YOUR_OPENROUTER_API_KEY"
export AGENT_PROXY=socks5h://127.0.0.1:10801

export AGENT_AUTH_MODE=oauth
export BIOAGENT_OAUTH_CLIENT_SECRET="YOUR_BIOAGENT_OAUTH_SECRET"
export AGENT_OAUTH_FLEXIBLE_HOST=true

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

python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

### Terminal 2 — MSCAN backend

```bash
conda activate openaisdk
export BIOAGENT_SECRET="$(
  python -c 'import json; print(json.load(open("runtime/website-integration/clients.json"))["mscan"]["secret"])'
)"
cd resource/mscan/mscan-app

export BIOAGENT_PORT=8000  # Must match Terminal 1.
export OAUTH_PORT=8090
export MSCAN_PORT=8080
export OAUTH_MSCAN_CLIENT_SECRET="YOUR_MSCAN_OAUTH_SECRET"

java -jar mscan-admin/target/mscan-admin.jar \
  --spring.profiles.active=druid
```

### Terminal 3 — MSCAN frontend

```bash
conda activate openaisdk
cd resource/mscan/mscan

pnpm --ignore-workspace run dev
```

Open MSCAN at `http://localhost:8848`, sign in, select a sample and open
**Ask assistant**. Confirm the assistant opens and MSCAN logout ends the
embedded session.

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

Use the **BioAgent pipeline job ID** from the current session with
`website_result_sync`. MSCAN retrieves the result directly from Cromwell.
Check `website_transfer_status(transfer_id)` for `state: imported`.

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

## After code or configuration changes

| Change | Required action |
| --- | --- |
| MSCAN frontend source | Reload the Vite development page or rebuild the production frontend. |
| MSCAN backend source or packaged configuration | Stop the backend, rebuild its JAR and restart it. |
| Agent frontend or embed SDK | Run `npm --prefix frontend run build`, then reload the browser. |
| Agent Python code | Restart BioAgent. Rebuild the Docker worker image when worker or tool code changes. |
| Dependencies or lockfiles | Reinstall the affected dependencies and rebuild that application/image. |
| Origins, URLs or credentials set at startup | Update the matching settings and restart the affected services. |

## Technical reference

The agent tools live under `tools/function_tools/website/`. The generic API,
origin and transfer contracts are documented in [web integration](web_integration.md).

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

After packaging the MSCAN backend, run the checks from the BioAgent root.

```bash
pnpm --dir resource/mscan/mscan --ignore-workspace run type:check
python -B -m web_bridge.tests.check_mscan_java --root resource/mscan/mscan-app
python -B -m web_bridge.tests.check_mscan_logout \
  --mscan-root resource/mscan/mscan-app
```

For live browser checks and their prerequisites, see
[MSCAN adapter validation](../web_bridge/adapters/mscan/README.md#validate).

# User accounts and isolated workers

BioAgent runs independently of Mscan. Network startup automatically enables
accounts, public registration, and Docker tool workers:

```bash
conda activate openaisdk
python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

Open `http://<server-ip>:8000` from your browser, then choose **Create account**.
No SSH tunnel is required. `0.0.0.0` is a listening address; use the server's IP
address in the browser. Direct HTTP is intended for LAN development. Use HTTPS
for internet deployment because HTTP does not encrypt passwords or cookies.

## Code organization

Authentication and isolation are root-level Python packages:

```text
auth/
  context.py          Principal, identity scope, modes and authorization errors
  store.py            Accounts, passwords, login tokens and rate limits
  ownership.py        Session ownership and deletion tombstones
  __main__.py         python -m auth administration commands
isolation/
  deploy/             Worker Dockerfile and Dockerfile-specific ignore rules
  policy.py           Execution policy, capabilities and WorkspaceAccess
  supervisor.py       Docker lifecycle, workspace exchange and container cleanup
  worker.py           Container entry point: python -m isolation.worker
  protocol.py         Bounded JSON control messages and relative paths
  files.py            Streaming snapshots and validated file imports
  limits.py           Shared storage and preview settings
  storage.py          Session/account quotas and disk reservations
  network.py          Host-side public HTTP broker
  network_client.py   Worker-side broker client
  provider_policy.py  Endpoint and method permissions for database adapters
  embeddings.py       Bounded embedding RPC with credentials kept on the server
  pipeline_policy.py  Workflow execution exclusions, separate from engine adapters
```

`auth` does not import isolation or the agent runtime. `isolation` uses auth and
receives a `WorkspaceAccess` containing the ownership store and workspace root.
It does not import `harness.runtime` or discover application stores through globals.
The application wires these dependencies through `harness.sandbox.execution_access()`
and `AgentRunContext.execution_access`; they are never model-supplied arguments.

HTTP authentication remains in `interfaces/auth.py`. The remote pipeline broker
lives in `tools/infrastructure/pipeline_engine/broker.py`, alongside the existing
pipeline engine. Web startup manages its polling thread separately from Docker
container cleanup. Database locations, ownership records, HTTP routes and execution
limits are unchanged by this reorganization.

Pipeline execution has one shared implementation:

- `pipeline_engine/service.py`: plan verification, input resolution and execution
  context creation through `prepare_execution()`, plus engine dispatch through
  `execute_engine()`.
- `pipeline_engine/engine/`: the original engine adapters. `cromwell.py` provides
  shared WDL preparation and a REST client used by both ordinary and isolated jobs.
- `pipeline_engine/broker.py`: ownership, private snapshots, credentials and bounded
  HTTP transport, disabled cross-account call caching, durable remote IDs, quotas,
  and scoped artifact publication. It delegates submission construction and remote
  operations to the shared Cromwell adapter.
- `isolated_controller.py`, `isolated_worker.py` and `isolation/`: detached process
  and container boundaries around `service.execute_engine()` for local engines.

The ordinary runner waits for Cromwell synchronously; the isolated reconciler polls
persisted IDs so server restarts do not replay submissions. These lifecycle choices
share the same protocol and preparation code. Isolation supplies its own bounded
transport and artifact registration instead of permitting host-path fallback.
Existing jobs without a recorded Cromwell API version continue using `v1`; new
jobs retain the manifest's version for submission, polling and cancellation.

After pulling this layout, rebuild the worker image and restart running agent
servers/workers together. The administration command is now `python -m auth`;
the old `python -m harness.auth` module path has been removed.

## Build the worker image

Docker must be running and accessible to the server account. The build files live
in `isolation/deploy/`. Run the command from the repository root: the final `.`
supplies the application packages as the build context. Rebuild after changing
worker/tool code or Python dependencies.

```bash
docker build -f isolation/deploy/Dockerfile -t bioagent-worker:local .
npm --prefix frontend run build
```

The Dockerfile copies only application code and requirements. Its dedicated
ignore file excludes runtime data, local environments, resources, and secrets.
The image has its own Python dependencies; users cannot modify the host's conda
environment through a tool call. `AGENT_WORKER_IMAGE` can select an administrator-built
image. It must implement worker protocol 3 and carry the matching image label;
stale images produce a rebuild error. Images are never pulled
implicitly during a user request.

The web server can start without Docker, so login and file/history access remain
available. Agent execution returns an actionable error if the worker image or
Docker daemon is unavailable. It never silently falls back to host execution.

## Startup modes

| Startup/configuration | Account access | Tool execution |
| --- | --- | --- |
| `--host 127.0.0.1`, no explicit mode | Local owner, no login | Existing local executor |
| `--host 0.0.0.0`, no explicit mode | Multi-user login and registration | Isolated Docker workers |
| `AGENT_AUTH_MODE=multiuser`, loopback listener | Multi-user login and registration | Isolated Docker workers |
| `AGENT_AUTH_MODE=cas` | CNCB CAS users; passwords and registration disabled | Isolated Docker workers |
| `AGENT_AUTH_MODE=oauth` | Shared CNCB OAuth broker; passwords and registration disabled | Isolated Docker workers |
| Explicit `AGENT_AUTH_MODE=local`, network listener | Rejected | None |

Explicit settings are honored. If you previously exported `AGENT_AUTH_MODE=local`,
unset it before using automatic network startup. Local mode stays loopback-only:

```bash
python -B -m interfaces.web --host 127.0.0.1 --port 8000
```

Local and registered accounts have separate conversations. Switching startup mode
does not change ownership or automatically transfer existing conversations.

## Model and remote service settings

Set the model credential in the server's terminal before startup. If model access
requires the local SOCKS proxy, configure it in that same terminal:

```bash
export OPENROUTER_API_KEY='your-openrouter-api-key'
export AGENT_PROXY=socks5h://127.0.0.1:10801
```

Omit `AGENT_PROXY` when a proxy is not needed. The model client runs on the trusted
server. Model requests and the public GET broker can use this proxy; tool containers still have no network interface. Install `requests[socks]` from `requirements.txt` for the broker proxy client.
Never copy provider or storage credentials into the worker image or browser.

The remote service configuration verified on 2026-11-03 is:

| Setting | Value |
| --- | --- |
| Cromwell | `http://192.168.164.46:39000` |
| S3 endpoint | `http://192.168.164.46:7070` |
| Input storage | `s3://cncb-web-server-mic/files` |
| Output storage | `s3://cncb-web-server-mic/cromwell/outputs` |
| Region | `us-east-1` |
| Input mount prefix | `/data/versitygw/data/s3` |
| Output mount prefix | `/data/versitygw/data/s3/cncb-web-server-mic/cromwell/outputs` |
| Execution path prefixes | `/data/zhaomh/cromwell-workspace/cromwell-executions`, `/cromwell-share/cloud_cromwell/cromwell-executions` |

Use the complete [Cromwell/S3 environment example](web_usage.md#wdl-execution-backend)
and supply your own access key and secret outside source control. Output downloads
reuse the input-storage endpoint, region, and credentials. Restart the server
after changing environment settings; exporting variables in another terminal
does not update an already-running process.

These settings enable the authenticated Cromwell/S3 adapter for WDL plugins.
Shell, Snakemake, and Nextflow plugins run in disposable workers without Cromwell. Containers retain
`--network=none` and receive no storage credentials. The executable catalog remains
narrower than the local/trusted catalog. The UI retains all six Quick starts and
the full More pipelines catalog, with individual availability messages from
`GET /config`. These describe adapters and configuration, not live provider health.
Displaying an entry does not authorize execution; the broker separately enforces
the workflow safety policy and session ownership.

## Registration and authentication

`GET /auth/status` returns the mode, `registration_enabled`, and the current user
or null. In `multiuser` mode, `POST /auth/register` accepts only the identity
fields it needs:

```json
{"username": "alice", "password": "a-long-unique-password"}
```

A successful registration returns HTTP 201 and signs the user in with an HttpOnly
cookie. User IDs are generated on the server. Supplied owner IDs, roles, or admin
flags have no effect. Usernames are unique and case-sensitive, use 1–100 letters,
digits, or `_.@-`, and cannot be `local`. Passwords require 12–1024 characters and
are salted and hashed using PBKDF2-HMAC-SHA256 with 600,000 iterations.

Duplicate usernames return 409; invalid input returns 400. Registration permits
five attempts per connecting client per hour, including invalid attempts; excess
attempts return 429. Login has separate per-account and per-client throttling.
Behind a proxy, the connecting client may be the proxy; the server deliberately
does not trust arbitrary forwarded-IP headers. Configure proxy-level limits too.

Disable new registrations while keeping existing logins:

```bash
export AGENT_REGISTRATION=false
```

Administrators can still create accounts or reset passwords using hidden prompts:

```bash
python -m auth add-user alice
python -m auth set-password alice
```

There is no public administrative role. Password changes revoke all logins for
that user. Logout revokes the current login and the user's website bindings.
Cookies expire after eight hours, use SameSite=Lax, and are stored as hashes in
`AGENT_AUTH_DB` (default `runtime/auth.sqlite3`). HTTP uses a non-Secure cookie;
HTTPS public origins require Secure cookies. Browser-origin checks protect state
changes, including registration and login. UI account changes clear old chat
state across tabs.

### Direct CNCB CAS login

CAS mode makes BioAgent validate its own CNCB tickets. Use it when BioAgent is a
separate CAS client and no shared OAuth broker is configured:

```bash
export AGENT_AUTH_MODE=cas
export AGENT_PUBLIC_ORIGIN=https://agent.example.com
export AGENT_CAS_LOGIN_URL=https://sso.cncb.ac.cn/login
export AGENT_CAS_VALIDATE_URL=https://sso.cncb.ac.cn/p3/serviceValidate
export AGENT_CAS_LOGOUT_URL=https://sso.cncb.ac.cn/logout
export AGENT_CAS_SERVICE_URL=https://agent.example.com/auth/cas/callback
export AGENT_CAS_LOGOUT_RETURN_URL=https://agent.example.com
```

Register the exact `AGENT_CAS_SERVICE_URL` in CAS. BioAgent validates each
single-use service ticket itself and requires the same `userId` attribute MSCAN
uses; this stable ID owns conversations, files and runs. The display username is
synchronized from CAS, but authorization never relies on it. Password login and
public registration are disabled in this mode.

The callback uses a five-minute HttpOnly state cookie to prevent login CSRF. CAS
service tickets are linked to hashed BioAgent login tokens so a back-channel CAS
`logoutRequest` immediately revokes the matching session. Application logout
first revokes BioAgent state, then enters CAS global logout.

### Shared OAuth service for MSCAN and BioAgent

For separate app sessions backed by one CNCB login service, run the standalone
broker in `oauth-service/`, register its `/cas/callback` with CNCB, then configure:

```bash
export AGENT_AUTH_MODE=oauth
export AGENT_PUBLIC_ORIGIN=https://agent.example.com
export AGENT_OAUTH_SERVER_URL=https://auth.example.org
export AGENT_OAUTH_CLIENT_ID=bioagent
export AGENT_OAUTH_CLIENT_SECRET=YOUR_BIOAGENT_OAUTH_CLIENT_SECRET
export AGENT_OAUTH_REDIRECT_URI=https://agent.example.com/auth/oauth/callback
export AGENT_OAUTH_POST_LOGOUT_REDIRECT_URI=https://agent.example.com/
export AGENT_OAUTH_PROXY=
```

### Development and production URLs

Use a dedicated BioAgent environment file per deployment. The development
profile uses the browser-visible IP address and port, for example
`http://192.168.1.100:8008`. The production profile uses:

```text
AGENT_PUBLIC_ORIGIN=https://mscan.cncb.ac.cn
AGENT_PUBLIC_BASE_URL=https://mscan.cncb.ac.cn/OneMicro/agent
AGENT_OAUTH_REDIRECT_URI=https://mscan.cncb.ac.cn/OneMicro/agent/auth/oauth/callback
AGENT_OAUTH_POST_LOGOUT_REDIRECT_URI=https://mscan.cncb.ac.cn/OneMicro/agent/
```

Run BioAgent with `AGENT_ENV_FILE=.env.development` or
`AGENT_ENV_FILE=.env.production`. Keep the OAuth broker URL and client secret
outside these tracked profile files. The reverse proxy must forward
`/OneMicro/agent/` to BioAgent and remove that prefix before the request reaches
the BioAgent listener.

Add the exact BioAgent and MSCAN server callbacks to the broker's private client
registry. The broker validates CNCB CAS tickets; each app exchanges an OAuth code
server-to-server and creates its own application session. See
[`oauth-service/README.md`](../../oauth-service/README.md) for broker setup and
MSCAN configuration. BioAgent logout revokes its local session first, then uses
the broker's authenticated logout-request endpoint; the broker owns CNCB CAS
logout and the registered final redirect. `AGENT_OAUTH_PROXY` is intentionally
separate from `AGENT_PROXY`; leave it empty for a broker on localhost. The
broker-issued `sid` is stored with each application login. Signed backchannel
logout events revoke matching BioAgent and MSCAN sessions, so logout propagates
across both applications.

## What is isolated

The trusted agent controller, model client, authentication, queue, and website,
public HTTP, and Cromwell/S3 brokers stay on the server. Model-directed workspace operations,
including **both synchronous and asynchronous** tool handlers such as `code_test`
and `python_execute`, run inside disposable containers.

Each container has:

- An unprivileged UID, a read-only image, dropped Linux capabilities, and
  `no-new-privileges`; Docker's default seccomp policy remains enabled.
- No direct network, Docker socket, host environment, provider credentials,
  authentication database, or other users' files. Only private, per-invocation
  staging directories are bind-mounted; application workspaces are never mounted.
- One CPU, 1 GiB memory with no extra swap, 64 processes, and a 180-second wall
  deadline by default. CPU, memory, and deadline can be configured separately
  from file storage.
- Selected inputs are streamed into a private disk-backed staging workspace.
  Operations that search a workspace or run code may require several files; tree
  listings use metadata without copying file bodies. Inputs cannot expose the
  original application workspace. JSON carries bounded control messages and tool
  results, never base64 copies of the workspace.
- A 10 GiB per-operation staging budget and 100,000 filesystem entries by default.
  The supervisor reserves disk space before staging, monitors usage while the
  container runs, stops over-budget workers, and validates output sizes before import.
  Monitoring is not a filesystem-enforced hard quota: a fast writer can exceed
  the budget between checks. Use filesystem quotas for strict disk isolation.

The supervisor validates returned relative paths and sizes, rejects symlinks,
hard links, devices, and file/directory conflicts, and imports only changed
regular files. Concurrent changes are detected before import. Workspace operations
within one session are serialized across controller processes. Detached pipelines
run against private snapshots, with publication serialized separately so polling
does not wait for the whole pipeline. Timeout/cancellation
removes the container and its descendants; failed exchanges do not import files.
The server also reaps expired, labelled worker containers every 30 seconds,
including orphans left by a controller crash or a previous server process.

This profile supports uploaded-file analysis, reports, workspace code inspection
and edits, bounded Python/tests, local data tools, and compatible specialists.
The authenticated website bridge remains available through its host-side broker.

**Enabled network capabilities:** `web_fetch`, `web_search`, `pubmed_search`, and
`pdb_download` use the public GET broker. PDB downloads permit only HTTPS structure
URLs on `files.rcsb.org`, with the broker's existing 4 MiB response limit. Use
`pdb_download` followed by `structure_inspect` to download and inspect a structure;
the web UI renders PDB/mmCIF artifacts with its built-in interactive 3D viewer.
There is no separate viewer tool. Rebuild the worker image and restart the server
after updating the isolated tool adapters.
`ncbi_retrieval`, `alphafold_download`, `database_lookup`, and `blast_search`
reuse their existing provider implementations through a restricted HTTP adapter.
Only the required provider endpoints are reachable; POST is limited to RCSB JSON
search and BLAST form submission. Redirects are revalidated. Arbitrary request
headers, authentication, cookies, and proxy configuration do not cross the boundary.

`evidence_index` and `evidence_retrieve` use a bounded embedding RPC. Only the
configured embedding model is accepted; each request permits up to 64 texts of
12,000 characters each, with 512,000 characters total. Embedding credentials remain
on the server. Durable knowledge ingestion/status/retrieval use fixed host service
operations with ownership checks, a persistent queue/database, restricted public
crawling, and staged, quota-checked retrieval artifacts. The research specialist,
report reviewer, and report synthesizer are registered again; model calls stay on
the server while their workspace tools use the normal isolation routes.

`pipeline_shell` and the pipeline specialist use the pipeline broker described below.
Arbitrary code retains no network access. An unrelated large file no longer
blocks tools with explicit inputs. Session/account storage quotas cover server
uploads, isolated output imports, and private pipeline snapshots; trusted local
execution is not a filesystem quota boundary. A container does not provide a
separate kernel. Account-wide model spending limits still need deployment-level
budgets.

The historical shared executor remains available only for a closed group in
which **all existing accounts are trusted**:

```bash
export AGENT_AUTH_MODE=multiuser
export AGENT_REGISTRATION=false
export AGENT_WORKER_BACKEND=local
export AGENT_ALLOW_SHARED_EXECUTION=true
```

This removes the container boundary. Shared execution is rejected whenever public
registration is enabled. The default multi-user backend is always `docker`.

### Network retrieval and detached pipelines

`isolation/network.py` handles bounded public HTTP requests over the worker's
stdin/stdout protocol. It resolves and validates addresses, connects to the
validated IP (including through the optional SOCKS5 proxy), checks TLS against the
original hostname, and validates each redirect. Private/special-purpose addresses,
credentials in URLs, and ports other than 80/443 are rejected. With an active
`AGENT_PROXY`, hostname resolution defaults to Google DNS over HTTPS using a
fixed public resolver IP and TLS hostname verification; this avoids filtered local
DNS replies without relaxing address checks. Set `AGENT_PUBLIC_DNS=system` to
use system DNS, or `google` to select encrypted DNS explicitly. Direct connections
default to system DNS. Resolver failures are reported without an unsafe fallback.
Each invocation
allows at most 64 broker requests and 4 MiB per HTTP response; provider POST bodies
are limited to 128 KiB. `web_fetch` retains its
1.5 MB page limit. Search and PubMed requests have fixed endpoint restrictions.
No host credentials, cookies, application workspace mounts, or network interfaces enter containers.
Search providers can still rate-limit or reject requests; those failures are
reported without switching to unrestricted networking.

`tools/infrastructure/pipeline_engine/broker.py` accepts the existing `agent-pipeline`
protocol. Adapter selection is driven by each installed plugin's `runner.yaml`:
`shell`, `snakemake`, and `nextflow` use Docker workers; `wdl` uses Cromwell/S3.
There is no template-name adapter registry. Workflow safety exclusions remain in
`isolation/pipeline_policy.py`, separately from compatibility in
`tools/infrastructure/pipeline_engine/contracts.py`. A policy exclusion is shown
as a policy message, rather than claiming an engine adapter is missing.

Install an operator-managed pipeline folder under `tools/runtime_tools/pipelines/`
with the existing template contract: `runner.yaml`, an engine entrypoint or workflow,
declared inputs/outputs, and its configuration/dependencies. Catalog requests
discover it automatically; refresh the browser to update More pipelines. Local
execution mounts only the selected plugin folder read-only, so adding a compatible
plugin does not require a registry edit or image rebuild. New software dependencies
still need to be installed in the worker image; engine and reference-data
dependencies on Cromwell remain deployment configuration.

The adapter reads the declared WDL filename, input slots (including arrays),
parameter defaults/types/choices, and file output mappings. Optional absent WDL
outputs are skipped; file-array outputs retain every file. The adapter uploads
only declared file inputs, so a text parameter cannot upload a similarly named
host file. Parameters remain bounded and shell-safe; image/reference-path changes
are deployment configuration, and user files must use owned input slots.
Only operator-installed workflow source is executable; model-supplied shell text
or arbitrary workflow paths are not accepted.

Local plugins execute in detached controllers supervising disposable Docker
workers. Plans, input snapshots, and execution state remain private on the host.
Engine caches stay in worker scratch space; only declared results are imported.
Scratch accounting counts temporary links without following them. Published
workspace files still reject links and devices.
The image includes Snakemake, Java, and the complete checksum-verified
[Nextflow 25.10.9 distribution](https://github.com/nextflow-io/nextflow/releases/tag/v25.10.9)
for offline execution. The controller survives a web-server restart; if the
controller itself dies, status becomes `interrupted` without resubmission.
Cancellation removes its worker. Local plugin deadlines are capped by
`AGENT_WORKER_TIMEOUT_SECONDS`.

The shared broker and remote WDL path enforce these rules:

- Ownership is checked against the authenticated session on every operation.
- Plans and immutable input snapshots live under
  `AGENT_METADATA_DIR/.pipelines/<session_id>`, outside model-writable workspaces.
  Editing an upload after planning does not change the approved snapshot.
- Template parameters are validated before submission, including restrictions on
  strings interpolated by the existing workflow. Cromwell call caching is disabled.
- The broker stages inputs through configured S3 storage and retains the remote
  job ID. Status, cancellation, and collection use that persisted ID. A browser,
  controller, or web-server restart does not resubmit a workflow.
- Ambiguous submissions become `interrupted` and require operator reconciliation;
  they are never automatically retried and continue reserving an active-job slot
  until reconciled. Cancellation remains pending until the
  remote service confirms termination. Deadlines trigger remote abort requests.
- Output downloads must map into configured S3 storage and contain this workflow's
  ID as a path component. There is no fallback to reading a host-local path.
  Completed jobs register owned remote artifact references, including their size
  and object version/ETag. For filesystem-backed S3 gateways that omit both,
  references retain the modification timestamp and size; downloads validate both
  against the GET response before serving it. This fallback detects metadata
  changes but is not a cryptographic content-identity guarantee. Downloads stream through the authenticated server;
  storage credentials remain private. Workspace **Import** copies a selected
  artifact into local storage and records its SHA-256 checksum. ZIP bundles are
  generated only when requested, use a temporary disk reservation, and are removed
  after download. `results` includes small text previews within the shared preview
  byte budget, allowing the agent to summarize small outputs without importing
  every artifact. Existing locally collected job outputs remain readable.
- Limits are two active pipeline jobs per account, sixteen server-wide, thirty-two
  pending plans per session. Remote artifact references do not consume local file
  quotas. Explicit imports use the configured per-file/session/account limits.
  Artifact-registration failures preserve remote execution success and can be
  retried with `results`; they do not launch another workflow.
- A background reconciler polls persisted active jobs every five seconds between
  polling rounds. Recoverable service outages
  retain their IDs and are retried. Once Cromwell confirms success, the job is
  marked successful even if output registration fails; `artifact_status` reports
  availability separately. Retrying `results` retries collection, never execution.

After updating, install requirements, rebuild the worker image and frontend, then
restart the server with the Cromwell/S3 environment above:

```bash
python -m pip install -r requirements.txt
docker build -f isolation/deploy/Dockerfile -t bioagent-worker:local .
npm --prefix frontend run build
python -B -m interfaces.web --host 0.0.0.0 --port 8000
```

Try “Fetch https://example.com/ and summarize it” or “Run the bundled WDL template
demonstration and report its metrics.” The latter presents a saved plan for
approval before submitting a remote job.

## HTTPS and domains

For an internet-facing service, use a TLS reverse proxy:

```bash
export AGENT_AUTH_MODE=multiuser
export AGENT_PUBLIC_ORIGIN=https://agent.example.com
python -B -m interfaces.web --host 127.0.0.1 --port 8000
```

Forward the original Host header and keep the backend private. The public origin
is an exact scheme/host/port. Without it, direct HTTP accepts numeric IP hosts,
localhost, and the machine hostname; unrelated domain names are rejected to
limit DNS rebinding. Browser requests that change state must match the origin.
Do not set `AGENT_AUTH_COOKIE_SECURE=true` for plain LAN HTTP: browsers will not
send that cookie over an insecure connection.

## Existing conversations

Old ownerless conversations are preserved but hidden until assigned explicitly.
Stop the server and workers and back up `runtime/` before migration. Preview:

```bash
python -m auth adopt-legacy --user local
```

Apply the displayed assignment:

```bash
python -m auth adopt-legacy --user local --apply
```

Replace `local` with an existing username to adopt into a registered account.
Already-owned sessions are never reassigned. Legacy queue rows inherit the owner;
unfinished old runs are interrupted rather than replayed. Old website bindings
must reconnect.

## Ownership and integration

The ownership registry is `AGENT_METADATA_DIR/.ownership.sqlite3`, normally
`runtime/session_metadata/.ownership.sqlite3`. Sessions, histories, uploads,
downloads, jobs, events, approvals, knowledge resources, and bridge bindings check
ownership. Inaccessible resources return 404; missing/expired authentication
returns 401. Deleted session IDs retain tombstones and cannot be reclaimed.
Workers reconstruct identity from trusted queue records. SSE readers revalidate
login state while polling. Running work can finish after the browser signs out.

The UI obtains session IDs through `POST /sessions`. Existing API clients can
propose new IDs for uploads/runs, but cannot replace an existing owner's claim.
Back up authentication, ownership, metadata, history, and queue databases together.

In multi-user mode, the web bridge maps a trusted website's authenticated
`(site_id, external_subject)` to a BioAgent account. New external identities receive
separate accounts; an administrator can explicitly link an existing account before
first use. Usernames and email addresses are not automatically matched. Linked
access uses the account's normal permissions, including session and file ownership.

The website backend authenticates with a private service credential configured
through `AGENT_WEBSITE_CLIENTS_FILE` or `AGENT_WEBSITE_CLIENTS`. The embedded
assistant exchanges a single-use login code for an in-memory bearer credential,
so this flow does not depend on third-party cookies. Website logout revokes that
site's login sessions and bindings; it does not remove the persistent identity
mapping. Project sharing and ownership transfer are not implemented.

See [the generic web integration guide](web_integration.md#independent-website-accounts-and-durable-results)
for identity linking, credentials, origins, and data exchange, and
[the MSCAN web bridge guide](mscan_web_bridge.md) for MSCAN installation and usage.
The isolation rules in this document apply to standalone and embedded use alike.

## Verification

```bash
python -m unittest evals.test_user_isolation evals.test_isolated_workers evals.test_isolated_brokers -v
AGENT_TEST_DOCKER=1 python -m unittest evals.test_isolated_workers evals.test_isolated_brokers -v
python -m unittest evals.smoke_session_history web_bridge.tests.test_protocol evals.smoke_web_contract evals.smoke_approvals -v
AGENT_TEST_DOCKER=1 python -m unittest evals.test_tool_compatibility -v
npm --prefix frontend run build
```

Docker tests run real containers, execute a scripted-model tool call, verify
artifact/history return, probe host/other-user/network/credential denial, reject
symlink exports, and verify container removal after timeout. They use temporary
state and do not call a paid model or external analysis service.

The compatibility suite compares local and isolated tool registration, exercises
provider downloads/submission/polling in real containers with deterministic HTTP
fixtures, tests evidence embedding RPC and durable knowledge ownership, and runs
the four local pipeline templates through actual engines and artifact downloads.
Provider and embedding fixtures verify adapter behavior, not external uptime or
paid model quality. It also checks cancellation, interrupted controllers, and
missing configuration messages. Browser validation is available through
`python -m evals.check_web_multitasking` after building the frontend.

`python -m unittest evals.test_pipeline_plugins -v` tests discovery and WDL
submission using temporary non-biological fixtures and mocked remote services.
Set `AGENT_TEST_DOCKER=1` to also execute a newly installed text-processing plugin
in the existing worker image and verify owned output publication. These checks
exercise agent integration; they do not retest the production biology workflows.

Compatibility validation on 2026-11-03 passed the provider/embedding fixtures,
durable knowledge checks, real Docker boundary tests, and all four local engine
templates with owned result files and ZIP downloads. Live isolated downloads of
AlphaFold P69905 and NCBI NM_000518 succeeded; the host broker also received HTTP
200 and parsed JSON from QuickGO for GO:0008150. These checks used temporary
owned workspaces and no paid model calls. The browser check confirmed readiness
labels, retained Quick starts, and concurrent conversation behavior. The existing
Cromwell broker regression tests passed; no new live Cromwell job was submitted
in this compatibility pass.

## Live validation: 2026-11-03

These observations were recorded on 2026-11-03 (Asia/Shanghai), using real
OpenRouter requests and synthetic CSV data. They are separate from the offline
and scripted-model tests above.

| Check | Observed result |
| --- | --- |
| LAN HTTP browser | Registration, login, persisted answers, workspace artifacts, and logout passed |
| Account isolation | A second account received 404 for another account's history, runs, generated files, and approvals; unauthenticated access received 401 |
| GPT-OSS table analysis | Real `file_inspection`, `table_profile`, and `table_group` calls returned correct counts and means |
| Python proposal review | GPT-OSS produced invalid Python twice; both proposals were rejected before execution |
| GPT-5.6 Sol export | With corrected Python supplied in the request, the model requested approval; the reviewed code ran in the isolated worker and produced a verified CSV |
| Cromwell at `.46` | `/engine/v1/version` returned HTTP 200 and version 91 |
| S3 at `.46` | Authenticated upload, download/byte comparison, deletion, and confirmation of deletion passed for a new synthetic object |
| Output storage | Listing the configured output prefix returned HTTP 200; existing object contents were not downloaded |
| Server configuration update | Existing test accounts and conversation history survived the restart with the updated settings |

The final downloaded `summary.csv` contained:

```csv
group,count,sum,mean
A,2,30.0,15.0
B,2,70.0,35.0
```

The earlier `.39` address timed out; the replacement `.46` address resolved that
connectivity problem. A subsequent broker validation submitted `template_wdl`
with the synthetic sequence `ACGTACGT` to `.46`. It succeeded and returned three
verified artifacts: report, metrics, and normalized sequence. Metrics were length
8 and GC 50%. A real isolated worker also retrieved `https://example.com/`.
PubMed retrieval also returned a real literature record. DuckDuckGo returned a
browser-verification challenge (HTTP 202); `web_search` reports that limitation
explicitly instead of returning misleading empty evidence. The web API verified
owner downloads (200) and other-account denial (404), and a real model requested
approval for a second template job before successful execution. A further
remote job completed across a web-server restart. A separate live cancellation
was confirmed as `Aborted` by Cromwell and `cancelled` by the broker. Verified
public download paths
use `outputs/pipelines/<job_id>/...`. Automated validation passed 84 account,
worker, and broker tests plus 8 pipeline runtime/completion tests.
The broker regression tests cover private destinations and redirects, DNS pinning,
private plan snapshots, cross-account denial, persisted polling/cancellation,
ambiguous submissions, and output scope.

At validation time, the separate test instance used
`http://192.168.75.56:8010`; the older server on port 8000 was left unchanged.
The test instance used its own state directory rather than the default account
and conversation databases. This is a recorded test address, not a deployment
default or a guarantee that the process is still running.

Local evidence is under `runtime/live-validation/20261103T041352Z/`, including
`report.json`, `connectivity-update.json`, `verified-summary.csv`, and browser
screenshots. `runtime/live-validation/latest.json` records the test instance's
state directory and PID. These artifacts are Git-ignored and are not included
in a fresh checkout. Supplied API and storage credentials are omitted from this
documentation and the validation reports.


## File storage and large uploads

All values below are bytes except the entry count. Configure them on the server;
`GET /config` exposes effective storage limits to the web UI. Changing a preview
budget does not change how much data a user may store.

| Environment setting | Default | Scope |
| --- | --- | --- |
| `AGENT_MAX_UPLOAD_BYTES` | 268435456 (256 MiB) | Legacy multipart request, streamed to disk |
| `AGENT_MAX_FILE_BYTES` | 5368709120 (5 GiB) | Resumable upload, local import, worker output file |
| `AGENT_UPLOAD_CHUNK_BYTES` | 8388608 (8 MiB) | One resumable upload chunk |
| `AGENT_SESSION_STORAGE_BYTES` | 21474836480 (20 GiB) | Local session files plus private pipeline storage |
| `AGENT_ACCOUNT_STORAGE_BYTES` | 53687091200 (50 GiB) | Owned sessions, retained private files, pending uploads |
| `AGENT_WORKER_STORAGE_BYTES` | 10737418240 (10 GiB) | Per-invocation workspace and temporary files |
| `AGENT_WORKER_MAX_FILES` | 100000 | Filesystem entries per scanned/staged tree |
| `AGENT_MIN_FREE_DISK_BYTES` | 1073741824 (1 GiB) | Disk headroom after reservations |
| `AGENT_PREVIEW_BYTES` | 65536 (64 KiB) | File-inspection page |
| `AGENT_SEARCH_SCAN_BYTES` | 268435456 (256 MiB) | Text scan per file; incomplete scans are reported |

`AGENT_WORKER_MEMORY_BYTES` defaults to 1073741824, `AGENT_WORKER_CPUS` to 1,
and `AGENT_WORKER_TIMEOUT_SECONDS` to 180. Raising storage limits does not raise
memory or execution time. Format-specific parser limits still apply, including
the PDF reader's 128 MiB/2,000-page budget. Code, logs, website callbacks, and
model-visible responses retain separate bounded payloads.

Deleting a chat does not block quota checks for other chats. Account accounting
includes any retained workspace files and private pipeline snapshots belonging
to deleted sessions, while those sessions remain inaccessible. This also applies
to uploads and tool-result publication, including NCBI downloads.

In isolated mode, pipeline example files obey the same per-file, session, account,
and free-disk limits. Pending uploads count toward these checks. Example copying
reserves disk space and publishes a complete directory atomically; quota rejection
or copy failure leaves no partial example files or active reservation.

The web UI uploads in resumable chunks and retains an upload ID locally. Reselect
the same file in the same session after interruption to resume it. The server
checks ownership, total declared size, committed offset, and quota reservations.
Pending uploads expire after 24 hours and are cleaned on upload-service access.
Incomplete chunks roll back to the last committed offset. Completed files are
published atomically; retrying completion returns the same file. Upload staging
and the final copy are included in conservative free-disk reservations.

| Endpoint | Purpose |
| --- | --- |
| `POST /workspace/uploads` | JSON: `session_id`, `filename`, `size`; reserve an upload |
| `GET /workspace/uploads/<id>` | Read the committed `offset` |
| `PATCH /workspace/uploads/<id>` | Raw chunk with `Upload-Offset` and `Content-Length` |
| `POST /workspace/uploads/<id>/complete` | Publish the completed file |
| `DELETE /workspace/uploads/<id>` | Cancel and release the reservation |
| `GET /workspace/file?...` | Stream local or owned remote files; supports a single HTTP byte range |
| `POST /workspace/pipeline-artifacts/materialize` | JSON: `session_id`, `path`; import an owned remote output |

Remote outputs appear in the Workspace panel with **Download** and **Import**.
Import creates an ordinary workspace path for file-analysis tools. Pipeline
`results` returns an on-demand `pipeline-bundles/<job_id>/results.zip` path; pass
it to the authenticated workspace-file endpoint to download a bundle.

File inspection returns `truncated` and `next_offset` for bounded previews;
counts that would require a full scan are null. Workspace/code searches report
partial scans rather than silently treating skipped files as having no matches.
Session files larger than 32 MiB no longer prevent unrelated tool operations.

## Concurrent conversations in the web UI

Separate conversations can run at the same time. `AGENT_RUN_WORKERS` controls
the server-wide agent concurrency (default `3`); excess jobs wait in the queue.
The queue allows one active run or pending approval per session. This limit is
separate from Docker tool-worker resource limits.

The main page keeps each conversation’s messages, draft, files, progress and
approvals separate while you navigate. A running chat does not disable New chat
or another chat’s composer. Conflicting edits in the working chat stay disabled.
Short event polls keep browser connections available; reload reconnects to
existing queued/running jobs without resubmitting them. Drafts remain in page
memory until reload/logout. Closing the page does not cancel backend work.

The main chat's **Stop** button sends an authenticated cancellation request to
`POST /runs/<run_id>/cancel`. Queued requests stop before execution. Running
requests cancel cooperatively, clean up active tool calls, and request cancellation
of pipelines launched by that request. The button shows **Stopping** until the
agent confirms cancellation; remote workflows may still be awaiting their backend's
abort confirmation. Other conversations are unaffected. Reloading an active chat
restores its Stop control. Closing or navigating away from a chat does not stop it.

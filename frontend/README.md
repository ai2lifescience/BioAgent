# Pipeline2Agent frontend

The workspace, embedded assistant, and host-page demo are React + TypeScript applications built with Vite. This directory owns the browser source and public assets. The Python server serves the generated `frontend/dist` directory alongside the existing JSON and SSE API.

## Structure

- `src/components/AuthGate.tsx` gates all pages on local identity or an authenticated login, and clears displayed state on logout/account changes. See [account setup](../docs/user_isolation.md).
- `src/api.ts` owns typed JSON, SSE, and resumable event polling. The main workspace uses short polls; the single embedded conversation retains SSE.
- `src/types.ts` defines the backend envelopes shared by chat, sessions, workspace files, evidence, and runtime traces.
- `src/features/chat/ConversationPane.tsx` owns one conversation’s state and background run monitoring. Visited panes stay mounted while hidden so switching cannot redirect pending callbacks to another chat.
- `src/App.tsx` composes the workspace shell from session navigation, quick starts, chat messages, runtime details, the composer, and workspace files.
- `src/features/` groups the assistant, chat composer, messages and artifact viewers, session navigation, and workspace panel by responsibility. The generic host-page demo and bridge frontend components live in `web_bridge/frontend/` at the repository root.
- `src/components/icons.tsx` is the shared legacy robot mark and line-icon set used by every page; `AppErrorBoundary.tsx` turns malformed runtime payloads into a recoverable UI state.
- `src/styles.css` defines the workspace design system; feature styles live beside their components.
- `index.html`, `assistant.html`, and `assistant-demo.html` are the three Vite page entries. Their public URLs remain `/`, `/assistant`, and `/assistant-demo`.
- `web_bridge/frontend/embed.ts` at the repository root is the standalone embed-client source. The build emits `dist/static/assistant-embed.js`, served at the stable `/static/assistant-embed.js` URL. `public/favicon.svg` supplies the app icon.
- `dist/` contains generated HTML and hashed JavaScript/CSS assets under `static/`. It is ignored by Git and recreated on each build. Do not edit it directly.

## Build and run

With Node.js/npm and the project's Python dependencies installed, run from the repository root. For the Conda environment used by this project, install Node.js once with:

```bash
conda install -n openaisdk -c conda-forge nodejs
```

Then build and run:

```bash
npm --prefix frontend ci
npm --prefix frontend run build
python -B -m interfaces.web --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The build checks TypeScript before creating a clean `dist/`. Rebuild after changing UI source or public assets, and deploy the complete build directory with the Python server. The server does not compile the frontend on startup.
Keep the Python process working directory at the repository root. Runtime
defaults are relative to that directory; starting the backend from `frontend/`
would create a second `frontend/runtime/` tree.

## Frontend development

Keep the Python server running in one terminal. In another terminal, run:

```bash
npm --prefix frontend run dev
```

Open the URL printed by Vite. Vite serves its own frontend assets and proxies API requests to `http://127.0.0.1:8000`. To use a different backend:

```bash
VITE_BACKEND_URL=http://127.0.0.1:8123 npm --prefix frontend run dev
```

The backend is required for sessions, uploads, runs, and the website bridge. Website embedding also requires the exact browser origin to be allowed by the backend; see the [integration guide](../docs/web_integration.md).

Conversation databases, uploaded files, and job state remain in the repository-root `runtime/` directory (or configured external persistence paths). They are separate from this directory and are never part of the Vite build.

## Browser concurrency check

After building, run `python -m evals.check_web_multitasking` with Playwright and
Chrome installed. It exercises overlapping jobs, chat switching, drafts,
background uploads, approvals, reconnection and reload against local fixtures.
It does not call models or execute pipelines.

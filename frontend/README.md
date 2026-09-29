# Pipeline2Agent frontend

The workspace, embedded assistant, and host-page demo are React + TypeScript applications built with Vite. This directory owns the browser source and public assets. The Python server serves the generated `frontend/dist` directory alongside the existing JSON and SSE API.

## Structure

- `src/api.ts` owns typed JSON and SSE transport, including abortable runs.
- `src/types.ts` defines the backend envelopes shared by chat, sessions, workspace files, evidence, and runtime traces.
- `src/App.tsx` composes the workspace shell from session navigation, quick starts, chat messages, runtime details, the composer, and workspace files.
- `src/features/` groups the assistant, demo, chat composer, messages and artifact viewers, session navigation, and workspace panel by responsibility.
- `src/components/icons.tsx` is the shared legacy robot mark and line-icon set used by every page; `AppErrorBoundary.tsx` turns malformed runtime payloads into a recoverable UI state.
- `src/styles.css` defines the workspace design system; feature styles live beside their components.
- `index.html`, `assistant.html`, and `assistant-demo.html` are the three Vite page entries. Their public URLs remain `/`, `/assistant`, and `/assistant-demo`.
- `public/static/assistant-embed.js` is the standalone client for external websites, published at the stable `/static/assistant-embed.js` URL. `public/favicon.svg` supplies the app icon.
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

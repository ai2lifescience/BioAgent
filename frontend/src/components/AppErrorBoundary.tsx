import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props { children: ReactNode }
interface State { error: Error | null }

/** Keeps a malformed runtime payload from taking down the whole shell. */
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the diagnostic available in browser devtools without leaking it into
    // the visible product UI or server logs.
    console.error('Pipeline2Agent render error', error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return <main className="app-error-state" role="alert">
      <div className="app-error-card">
        <span className="eyebrow">Workspace paused</span>
        <h1>This response could not be displayed.</h1>
        <p>The run may still be available in the conversation. Reload the workspace to try again.</p>
        <button type="button" onClick={() => window.location.reload()}>Reload workspace</button>
      </div>
    </main>;
  }
}

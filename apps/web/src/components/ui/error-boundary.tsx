import { Component, type ErrorInfo, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, RefreshCw } from "lucide-react";

type Props = { children: ReactNode; fallback?: ReactNode };
type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    if (this.props.fallback) return this.props.fallback;
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas p-8">
        <div className="max-w-md text-center">
          <AlertTriangle className="mx-auto h-10 w-10 text-danger-text" strokeWidth={1.5} />
          <h1 className="mt-4 text-lg font-semibold text-ink">Something went wrong</h1>
          <p className="mt-2 text-sm text-mute">
            {this.state.error.message || "An unexpected error occurred."}
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
            <button
              type="button"
              onClick={() => this.setState({ error: null })}
              className="inline-flex items-center gap-1.5 rounded-[6px] border border-hairline bg-canvas px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-canvas-soft"
            >
              <RefreshCw className="h-4 w-4" strokeWidth={1.5} />
              Try again
            </button>
            <Link
              to="/documents"
              onClick={() => this.setState({ error: null })}
              className="inline-flex items-center gap-1.5 rounded-[6px] bg-ink px-4 py-2 text-sm font-medium text-[var(--canvas)] transition-colors hover:opacity-90"
            >
              Go to Documents
            </Link>
          </div>
        </div>
      </div>
    );
  }
}

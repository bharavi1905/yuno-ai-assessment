import React from "react";

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center h-full p-8">
          <div className="text-center bg-[#1a1d27] border border-[#ef4444]/40 rounded-xl p-8 max-w-md">
            <div className="w-12 h-12 rounded-full bg-[#2d0a0a] border border-[#ef4444]/30 flex items-center justify-center mx-auto mb-4">
              <svg viewBox="0 0 20 20" fill="#ef4444" className="w-6 h-6">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <h2 className="text-[#e8eaf0] font-semibold mb-2">Something went wrong</h2>
            <p className="text-[#7b7f9e] text-sm mb-6 font-mono">
              {this.state.error?.message ?? "An unexpected error occurred"}
            </p>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="px-4 py-2.5 bg-[#6c63ff] text-white text-sm font-medium rounded-lg hover:bg-[#574fd6] transition-colors"
            >
              Retry
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

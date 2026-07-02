import React, { Component } from 'react';

interface ErrorBoundaryState { hasError: boolean; message: string; }

export class ErrorBoundary extends Component<React.PropsWithChildren, ErrorBoundaryState> {
    constructor(props: React.PropsWithChildren) {
        super(props);
        this.state = { hasError: false, message: '' };
    }
    static getDerivedStateFromError(err: unknown): ErrorBoundaryState {
        const msg = err instanceof Error ? err.message : String(err);
        return { hasError: true, message: msg };
    }
    componentDidCatch(err: unknown, info: React.ErrorInfo) {
        console.error('[ErrorBoundary] Caught render error:', err, info);
    }
    render() {
        if (this.state.hasError) {
            return (
                <div className="error-boundary-container" style={{ padding: '2rem', textAlign: 'center', color: '#ef4444' }}>
                    <h2>⚠️ Something went wrong</h2>
                    <p>{this.state.message || 'An unexpected rendering error occurred.'}</p>
                    <button
                        onClick={() => this.setState({ hasError: false, message: '' })}
                        style={{ marginTop: '1rem', padding: '0.5rem 1rem', background: '#22c55e', border: 'none', borderRadius: '4px', cursor: 'pointer', color: '#000' }}
                    >
                        Try again
                    </button>
                </div>
            );
        }
        return this.props.children;
    }
}
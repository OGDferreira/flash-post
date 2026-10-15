import { Component, type ErrorInfo, type ReactNode } from "react";
import { RotateCw } from "lucide-react";

type Props = { children: ReactNode; resetKey?: string };
type State = { error: Error | null };

/** Catches render errors so one broken page does not blank the whole app. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("FlashPost page crashed", error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto mt-10 max-w-md rounded-2xl border border-danger/30 bg-danger-soft/70 p-5 text-center" role="alert">
        <h2 className="text-base font-semibold text-fg">Algo deu errado nesta tela</h2>
        <p className="mt-2 text-sm text-muted">O resto do FlashPost continua funcionando. Tente recarregar esta página.</p>
        <button className="btn-primary mx-auto mt-4" onClick={() => window.location.reload()} type="button">
          <RotateCw size={15} />
          Recarregar
        </button>
      </div>
    );
  }
}

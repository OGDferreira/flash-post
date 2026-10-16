import { Component, type ErrorInfo, type ReactNode } from "react";
import { RotateCw } from "lucide-react";

import { LoadingState } from "@/components/PageState";
import { isChunkLoadError, reloadOnce } from "@/lib/chunkReload";

type Props = { children: ReactNode; resetKey?: string };
type State = { error: Error | null; recovering: boolean };

const SOFT_RETRY_DELAY_MS = 400;

/**
 * Catches render errors so one broken page does not blank the whole app.
 * Recovers on its own before asking the user: a missing chunk (new deploy)
 * reloads the page; any other error first remounts the page once, then
 * reloads once, and only then shows the manual "Recarregar" screen.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, recovering: false };
  private softRetried = false;
  private timer: number | undefined;

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("FlashPost page crashed", error, info.componentStack);
    if (isChunkLoadError(error)) {
      if (reloadOnce()) this.setState({ recovering: true });
      return;
    }
    if (!this.softRetried) {
      this.softRetried = true;
      this.setState({ recovering: true });
      this.timer = window.setTimeout(() => this.setState({ error: null, recovering: false }), SOFT_RETRY_DELAY_MS);
      return;
    }
    if (reloadOnce()) this.setState({ recovering: true });
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey) {
      this.softRetried = false;
      if (this.state.error) this.setState({ error: null, recovering: false });
    }
  }

  componentWillUnmount() {
    window.clearTimeout(this.timer);
  }

  render() {
    if (!this.state.error) return this.props.children;
    if (this.state.recovering) return <LoadingState label="Carregando" />;
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

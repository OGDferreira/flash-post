import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowUpRight, Activity, Check, CircleAlert } from "lucide-react";

type HealthResponse = {
  status: string;
  service: string;
};

async function getHealth(): Promise<HealthResponse> {
  const response = await fetch("/health");
  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`);
  }
  return response.json() as Promise<HealthResponse>;
}

export default function App() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
  });

  const online = health.data?.status === "ok";

  return (
    <main className="relative flex min-h-screen flex-col overflow-hidden px-5 py-6 sm:px-8 lg:px-12">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_42%,rgba(83,109,254,0.09),transparent_48%)]" />

      <header className="relative mx-auto flex w-full max-w-7xl items-center justify-between">
        <a className="flex items-center gap-3" href="/" aria-label="FlashPost início">
          <span className="grid size-10 place-items-center rounded-xl border border-[#33447c] bg-[#11182d] text-sm font-bold tracking-tight text-[#9baaff]">
            F
          </span>
          <span className="text-base font-semibold tracking-[-0.03em] text-[#f5f7fb]">
            flashpost<span className="text-[#7186ff]">.</span>
          </span>
        </a>

        <div className="hidden items-center gap-2 rounded-full border border-[#202838] bg-[#0d1015] px-3 py-2 text-xs text-[#94a3b8] sm:flex">
          <Activity size={14} className="text-[#7186ff]" />
          Plataforma em preparação
        </div>
      </header>

      <section className="relative mx-auto flex w-full max-w-7xl flex-1 items-center py-16">
        <motion.div
          className="grid w-full items-center gap-12 lg:grid-cols-[1.15fr_0.85fr] lg:gap-20"
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
        >
          <div className="max-w-2xl">
            <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-[#27334a] bg-[#0d1015] px-3 py-1.5 text-xs font-medium text-[#aeb9ce]">
              <span className="size-1.5 rounded-full bg-[#536dfe]" />
              Nova geração de operações
            </div>

            <h1 className="max-w-xl text-5xl font-semibold leading-[1.04] tracking-[-0.065em] text-[#f5f7fb] sm:text-6xl lg:text-7xl">
              Sua operação,
              <br />
              <span className="text-[#7186ff]">em movimento.</span>
            </h1>

            <p className="mt-6 max-w-lg text-base leading-7 text-[#94a3b8] sm:text-lg">
              Estamos preparando um espaço mais claro para publicar, acompanhar
              resultados e cuidar de cada detalhe da sua operação.
            </p>

            <div className="mt-9 flex flex-wrap items-center gap-3">
              <div
                className={`inline-flex min-h-11 items-center gap-2.5 rounded-xl border px-4 text-sm font-medium ${
                  online
                    ? "border-[#1d3b37] bg-[#0c1715] text-[#9de6d1]"
                    : health.isError
                      ? "border-[#47252d] bg-[#1a1013] text-[#f1a3ad]"
                      : "border-[#202838] bg-[#0d1015] text-[#aeb9ce]"
                }`}
                role="status"
                aria-live="polite"
              >
                {online ? (
                  <Check size={16} />
                ) : health.isError ? (
                  <CircleAlert size={16} />
                ) : (
                  <Activity size={16} className="animate-pulse" />
                )}
                {online
                  ? "Sistema online"
                  : health.isError
                    ? "Status indisponível"
                    : "Verificando sistema"}
              </div>
              <span className="text-xs text-[#64748b]">
                {health.isError ? "Tente atualizar a página." : "FlashPost · 0.1"}
              </span>
            </div>
          </div>

          <div className="mx-auto w-full max-w-md lg:ml-auto">
            <div className="rounded-2xl border border-[#202838] bg-[#0d1015] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.28)] sm:p-6">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#64748b]">
                    Fundação
                  </p>
                  <h2 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-[#f5f7fb]">
                    Tudo começa aqui
                  </h2>
                </div>
                <span className="grid size-9 place-items-center rounded-lg border border-[#26345a] bg-[#121a31] text-[#8da0ff]">
                  <ArrowUpRight size={17} />
                </span>
              </div>

              <div className="mt-6 space-y-3">
                {[
                  ["Aplicação web", "React · TypeScript"],
                  ["API", "FastAPI · Python"],
                  ["Deploy", "Docker · Render"],
                ].map(([label, value], index) => (
                  <motion.div
                    key={label}
                    className="flex items-center justify-between gap-4 rounded-xl border border-[#1c2533] bg-[#0a0d11] px-4 py-3.5"
                    initial={{ opacity: 0, x: 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.14 + index * 0.1, duration: 0.35 }}
                  >
                    <span className="text-sm text-[#c7cfdd]">{label}</span>
                    <span className="text-right text-xs text-[#64748b]">{value}</span>
                  </motion.div>
                ))}
              </div>

              <div className="mt-5 flex items-center gap-2 border-t border-[#202838] pt-4 text-xs leading-5 text-[#64748b]">
                <span className="size-1.5 shrink-0 rounded-full bg-[#2dd4a0]" />
                Estrutura pronta para evoluir por módulos.
              </div>
            </div>
          </div>
        </motion.div>
      </section>

      <footer className="relative mx-auto flex w-full max-w-7xl items-center justify-between border-t border-[#161c26] py-4 text-xs text-[#64748b]">
        <span>FlashPost</span>
        <span>Construído para crescer com você.</span>
      </footer>
    </main>
  );
}

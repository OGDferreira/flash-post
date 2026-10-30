import { useQuery } from "@tanstack/react-query";

import { ErrorState, LoadingState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import { apiRequest } from "@/services/api";
import { brl } from "./api";

type Receipt = {
  id: string;
  offer_name: string;
  status: string;
  origin: string | null;
  origin_label: string;
  gateway: string | null;
  created_at: string | null;
  paid_at: string | null;
  gross: number | null;
  gateway_fee: number | null;
  gateway_net: number | null;
  flash_fee: number | null;
  platform_fee: number | null;
  commission_base: number | null;
  chief: { name: string; percent: number | null; amount: number | null; expected?: number | null } | null;
  seller: { name: string; amount: number | null };
  platform_total: number | null;
};

const GATEWAYS: Record<string, string> = { smokepay: "SmokePay", snakepay: "SnakePay", atenaspay: "Athenas Pay" };
const money = (value: number | null | undefined) => (value === null || value === undefined ? "—" : brl(value));

function Line({ label, value, tone = "text-fg", strong = false, hint }: { label: string; value: string; tone?: string; strong?: boolean; hint?: string }) {
  return (
    <div className={`flex items-baseline justify-between gap-3 px-3 py-2 ${strong ? "bg-surface-inset font-semibold" : ""}`}>
      <span className="text-sm text-fg-2">
        {label}
        {hint && <span className="block text-[11px] font-normal text-muted">{hint}</span>}
      </span>
      <span className={`shrink-0 text-sm tabular-nums ${tone}`}>{value}</span>
    </div>
  );
}

/** The "contracheque" of one sale: where every centavo went (Super Admin only). */
export function SaleReceiptModal({ orderId, onClose }: { orderId: string | null; onClose: () => void }) {
  const receipt = useQuery({
    queryKey: ["admin", "receipt", orderId],
    queryFn: () => apiRequest<Receipt>(`/api/admin/orders/${orderId}/receipt`),
    enabled: Boolean(orderId),
  });
  const data = receipt.data;
  return (
    <Modal open={Boolean(orderId)} onClose={onClose} title="Dados da venda" description={data ? `${data.offer_name} · ${data.origin_label}` : undefined}>
      {receipt.isLoading && <LoadingState label="Carregando venda" />}
      {receipt.error && <ErrorState message="Não foi possível carregar os dados desta venda." onRetry={() => void receipt.refetch()} />}
      {data && (
        <div className="space-y-4">
          <p className="text-xs text-muted">
            {data.paid_at ? `Paga em ${new Date(data.paid_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}` : `Status: ${data.status}`}
            {data.gateway && ` · ${GATEWAYS[data.gateway] ?? data.gateway}`}
          </p>
          <div className="divide-y divide-line-soft overflow-hidden rounded-xl border border-line-soft">
            <Line label="Valor da venda" strong value={money(data.gross)} />
            <Line label={`(−) Taxa do gateway${data.gateway ? ` (${GATEWAYS[data.gateway] ?? data.gateway})` : ""}`} tone="text-danger" value={money(data.gateway_fee)} />
            <Line label="(−) Taxa Flash por venda" tone="text-danger" value={money(data.flash_fee)} />
            {Boolean(data.platform_fee) && <Line label="(−) Taxa da plataforma" tone="text-danger" value={money(data.platform_fee)} />}
            <Line label="= Líquido após todas as taxas" strong value={money(data.commission_base)} hint="Base da comissão do chefe" />
          </div>
          <div>
            <h4 className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">Quanto ficou para cada um</h4>
            <div className="divide-y divide-line-soft overflow-hidden rounded-xl border border-line-soft">
              {data.chief && (
                <Line
                  hint={data.chief.percent !== null ? `${data.chief.percent.toLocaleString("pt-BR")}% sobre o líquido após as taxas` : undefined}
                  label={`${data.origin === "owner_all" ? "Dono do funil" : "Chefe"} · ${data.chief.name}`}
                  tone="text-accent"
                  value={money(data.chief.amount)}
                />
              )}
              {data.chief && data.chief.expected !== undefined && data.chief.expected !== null && data.chief.expected !== data.chief.amount && (
                <Line
                  hint="O split do gateway é definido antes do pagamento, com a taxa estimada"
                  label="Comissão pela regra (estimado × real)"
                  tone="text-warning"
                  value={`${money(data.chief.expected)} · dif. ${money((data.chief.amount ?? 0) - data.chief.expected)}`}
                />
              )}
              <Line label={`Vendedor · ${data.seller.name}`} tone="text-success" value={money(data.seller.amount)} />
              <Line label="Plataforma (taxas Flash)" value={money(data.platform_total)} />
              <Line label="Gateway" value={money(data.gateway_fee)} />
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}

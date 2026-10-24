import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Check, Share2 } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import type { Flow } from "@/features/bots/types";
import type { InstagramLoop } from "@/pages/loops/loopShared";
import { ApiError, apiRequest } from "@/services/api";
import { type FlowShare, type GatewayId, brl, useMyPartners, useSaveFlowShare } from "./api";

const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível salvar. Tente de novo.");
const SHOP_ID = /^(snakepay_[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$/;
const GATEWAY_NAMES: Record<GatewayId, string> = { smokepay: "SmokePay", snakepay: "SnakePay" };

type GatewayCatalog = { gateways: { id: GatewayId; name: string; available: boolean; fee: string }[] };

/** "80" / "80.5" / "80,5" → number with two decimals, or NaN. */
function parsePercent(value: string): number {
  const text = value.trim().replace(",", ".");
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(text)) return Number.NaN;
  return Math.round(Number(text) * 100) / 100;
}
const pct = (value: number) => `${value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
const complement = (value: string) => {
  const n = parsePercent(value);
  return Number.isNaN(n) || n > 100 ? "" : String(Math.round((100 - n) * 100) / 100);
};

/** Owner: share one funnel with one partner and set the rules of that share (gateway, the
 *  seller's part and the owner's commission, SnakePay ShopIDs), then confirm a summary.
 *  The backend validates everything again; the seller can never change these rules. */
export function FlowShareModal({ open, initial, onClose }: { open: boolean; initial: FlowShare | null; onClose: () => void }) {
  const partners = useMyPartners(open);
  const flows = useQuery({
    queryKey: ["bots", "flows"],
    queryFn: () => apiRequest<{ flows: Flow[] }>("/api/bots/flows/list"),
    enabled: open,
  });
  const loops = useQuery({
    queryKey: ["loops"],
    queryFn: () => apiRequest<{ loops: InstagramLoop[] }>("/api/loops?include_accounts=false"),
    enabled: open,
  });
  const catalog = useQuery({
    queryKey: ["payment-gateways"],
    queryFn: () => apiRequest<GatewayCatalog>("/api/payment-gateways"),
    enabled: open,
  });
  const save = useSaveFlowShare();

  const [step, setStep] = useState<"form" | "summary">("form");
  const [flowId, setFlowId] = useState("");
  const [partnerId, setPartnerId] = useState("");
  const [gateway, setGateway] = useState<GatewayId>("smokepay");
  const [seller, setSeller] = useState("");
  const [owner, setOwner] = useState("");
  const [ownerShop, setOwnerShop] = useState("");
  const [loopId, setLoopId] = useState<string | undefined>(undefined);
  const [takeAll, setTakeAll] = useState(false);

  useEffect(() => {
    if (!open) return;
    setStep("form");
    setFlowId(initial?.flow_id ?? "");
    setPartnerId(initial?.partner_id ?? "");
    setGateway(initial?.gateway ?? "smokepay");
    setSeller(initial ? String(initial.seller_percent) : "");
    setOwner(initial ? String(initial.owner_percent) : "");
    setOwnerShop("");
    setLoopId(undefined);
    setTakeAll(Boolean(initial?.owner_takes_all));
    save.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initial?.id, initial?.flow_id, initial?.partner_id]);

  const ownFlows = (flows.data?.flows ?? []).filter((flow) => !flow.from_template);
  const myLoops = (loops.data?.loops ?? []).filter((loop) => !loop.linked && !loop.from_template);
  const partnerList = partners.data?.partners ?? [];
  const snakeAvailable = catalog.data?.gateways.find((g) => g.id === "snakepay")?.available ?? false;
  const flow = ownFlows.find((item) => item.id === flowId);
  const partner = partnerList.find((item) => item.id === partnerId);
  const currentLoop = loopId === undefined ? (flow?.shared_loop_id ?? "") : loopId ?? "";
  // When editing, an empty ShopID field keeps the saved one (shown masked).
  const keepsOwner = Boolean(initial?.owner_shop_id) && !ownerShop.trim() && initial?.gateway === "snakepay";

  const problems = useMemo(() => {
    const list: string[] = [];
    const s = parsePercent(seller);
    const o = parsePercent(owner);
    if (!flowId) list.push("Escolha o funil.");
    if (!partnerId) list.push("Escolha o sócio vendedor.");
    if (takeAll) {
      // the percentages are not used while you keep 100%
    } else if (Number.isNaN(s) || Number.isNaN(o)) list.push("Preencha as duas porcentagens (até duas casas decimais).");
    else {
      if (s <= 0 || s > 100) list.push("A parte do vendedor precisa ser maior que 0% e no máximo 100%.");
      if (o < 0 || o >= 100) list.push("A comissão do dono vai de 0% até 99,99%.");
      if (Math.round((s + o) * 100) !== 10000) list.push("Vendedor + dono precisam somar exatamente 100%.");
    }
    if (gateway === "snakepay") {
      if (!snakeAvailable) list.push("A SnakePay ainda não foi liberada pelo administrador.");
      const ownerValue = ownerShop.trim();
      if (!takeAll && !Number.isNaN(o) && o > 0 && !ownerValue && !keepsOwner) list.push("Informe o seu ShopID SnakePay para receber a comissão.");
      if (ownerValue && !SHOP_ID.test(ownerValue)) list.push("O seu ShopID é inválido (começa com snakepay_).");
    }
    return list;
  }, [flowId, partnerId, seller, owner, gateway, snakeAvailable, ownerShop, keepsOwner, takeAll]);

  const confirm = () => {
    // With 100% for you the saved split stays for when you turn it off (100/0 when there is none).
    const validSplit = !Number.isNaN(parsePercent(seller)) && !Number.isNaN(parsePercent(owner)) && parsePercent(seller) > 0
      && Math.round((parsePercent(seller) + parsePercent(owner)) * 100) === 10000;
    const input = {
      flow_id: flowId,
      partner_id: partnerId,
      gateway,
      seller_percent: takeAll && !validSplit ? "100" : String(parsePercent(seller)),
      owner_percent: takeAll && !validSplit ? "0" : String(parsePercent(owner)),
      owner_takes_all: takeAll,
      ...(gateway === "snakepay" ? { owner_shop_id: ownerShop.trim() || undefined } : {}),
      ...(loopId !== undefined ? { loop_id: loopId || null } : {}),
    };
    save.mutate(input, { onSuccess: onClose });
  };

  const loading = partners.isLoading || flows.isLoading || catalog.isLoading;
  const s = parsePercent(seller);
  const o = parsePercent(owner);
  // A worked example on R$ 100,00 with SnakePay's public fee (3% + R$ 0,25); SmokePay's fee depends on the contract.
  const exampleNet = 100 - 3 - 0.25;
  const title = initial?.rule === "share" ? "Editar regras do compartilhamento" : "Compartilhar funil";

  return (
    <Modal
      busy={save.isPending}
      description="Você define as regras; o sócio vendedor só usa o funil e não consegue alterar porcentagem, gateway nem ShopIDs."
      footer={
        step === "form" ? (
          <div className="flex flex-wrap justify-end gap-2">
            <Button onClick={onClose}>Cancelar</Button>
            <Button disabled={problems.length > 0 || loading} onClick={() => setStep("summary")} variant="primary">
              Revisar
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap justify-end gap-2">
            <Button disabled={save.isPending} onClick={() => setStep("form")}>
              <ArrowLeft size={14} /> Voltar
            </Button>
            <Button disabled={save.isPending} onClick={confirm} variant="primary">
              <Share2 size={14} /> {save.isPending ? "Salvando…" : "Confirmar compartilhamento"}
            </Button>
          </div>
        )
      }
      onClose={onClose}
      open={open}
      title={title}
    >
      {loading ? (
        <LoadingState label="Carregando funis, sócios e gateways" />
      ) : step === "form" ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block space-y-1.5">
              <span className="text-sm font-medium text-fg">Funil</span>
              <select className="field !min-h-10 text-sm" disabled={Boolean(initial)} onChange={(e) => setFlowId(e.target.value)} value={flowId}>
                <option value="">Escolha um funil seu</option>
                {ownFlows.map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
            </label>
            <label className="block space-y-1.5">
              <span className="text-sm font-medium text-fg">Sócio vendedor</span>
              <select className="field !min-h-10 text-sm" disabled={Boolean(initial)} onChange={(e) => setPartnerId(e.target.value)} value={partnerId}>
                <option value="">Escolha um sócio</option>
                {partnerList.map((item) => (
                  <option key={item.id} value={item.id}>{item.name}{item.nickname ? ` (@${item.nickname})` : ""}</option>
                ))}
              </select>
            </label>
          </div>
          {partners.data && partnerList.length === 0 && (
            <p className="rounded-xl border border-warning/40 bg-warning-soft px-3 py-2 text-xs text-warning">
              Você ainda não tem sócios ativos. Convide um em Sócios e permissões.
            </p>
          )}

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-fg">Gateway das vendas deste compartilhamento</legend>
            <div className="grid grid-cols-2 gap-2">
              {(["smokepay", "snakepay"] as const).map((id) => {
                const available = catalog.data?.gateways.find((g) => g.id === id)?.available ?? false;
                return (
                  <button
                    aria-pressed={gateway === id}
                    className={`rounded-xl border px-3 py-2.5 text-left text-sm transition ${
                      gateway === id ? "border-accent bg-brand/10 text-fg ring-2 ring-accent/30" : "border-line-soft text-fg-2 hover:border-accent/60"
                    } ${available ? "" : "cursor-not-allowed opacity-50"}`}
                    disabled={!available}
                    key={id}
                    onClick={() => setGateway(id)}
                    type="button"
                  >
                    <span className="block font-semibold">{GATEWAY_NAMES[id]}</span>
                    <span className="block text-[11px] text-muted">
                      {available ? (id === "snakepay" ? "Split por ShopID, sem credencial do vendedor" : "Split por subconta, automático") : "Não liberado"}
                    </span>
                  </button>
                );
              })}
            </div>
          </fieldset>

          <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-line-soft bg-surface-inset p-3">
            <input checked={takeAll} className="mt-0.5 size-4 accent-[var(--color-accent)]" onChange={(e) => setTakeAll(e.target.checked)} type="checkbox" />
            <span className="space-y-0.5">
              <span className="block text-sm font-medium text-fg">Receber 100% das vendas</span>
              <span className="block text-xs leading-5 text-muted">
                Todo o dinheiro vai para a sua conta no gateway escolhido. O sócio não é avisado e não vê essas vendas, leads nem
                faturamento.
              </span>
            </span>
          </label>

          {!takeAll && (
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block space-y-1.5">
              <span className="text-sm font-medium text-fg">Parte do vendedor (%)</span>
              <input
                className="field !min-h-10 text-sm"
                inputMode="decimal"
                onChange={(e) => {
                  setSeller(e.target.value);
                  setOwner(complement(e.target.value));
                }}
                placeholder="ex.: 80"
                value={seller}
              />
            </label>
            <label className="block space-y-1.5">
              <span className="text-sm font-medium text-fg">Sua comissão de dono (%)</span>
              <input
                className="field !min-h-10 text-sm"
                inputMode="decimal"
                onChange={(e) => {
                  setOwner(e.target.value);
                  setSeller(complement(e.target.value));
                }}
                placeholder="ex.: 20"
                value={owner}
              />
            </label>
          </div>
          )}

          {gateway === "snakepay" && (
            <div className="space-y-3 rounded-xl border border-line-soft bg-surface-inset p-3">
              <p className="text-xs leading-5 text-muted">
                {takeAll
                  ? "Cada Pix é cobrado na sua conta SnakePay e o líquido inteiro fica com você."
                  : "Cada venda é cobrada na conta SnakePay do sócio, que precisa configurar a própria conta para usar o funil. Só a sua comissão vem via split para o seu ShopID."}
              </p>
              <label className="block space-y-1.5">
                <span className="text-xs font-medium text-fg-2">Seu ShopID SnakePay ({takeAll ? "recebe as vendas · não precisa se você tem chave própria" : "recebe a comissão"})</span>
                <input
                  autoComplete="off"
                  className="field font-mono text-xs"
                  onChange={(e) => setOwnerShop(e.target.value)}
                  placeholder={keepsOwner ? `Salvo (${initial?.owner_shop_id}) · deixe vazio para manter` : "snakepay_…"}
                  spellCheck={false}
                  value={ownerShop}
                />
              </label>
            </div>
          )}

          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-fg">Loop junto (opcional)</span>
            <select className="field !min-h-10 text-sm" onChange={(e) => setLoopId(e.target.value)} value={currentLoop}>
              <option value="">Sem loop</option>
              {myLoops.map((loop) => (
                <option key={loop.id} value={loop.id}>{loop.name}</option>
              ))}
            </select>
            <span className="block text-xs text-muted">O sócio recebe o loop pronto, sem contas: começa a postar quando ele conectar as dele.</span>
          </label>

          {problems.length > 0 && (seller || owner || flowId || partnerId) && (
            <ul className="space-y-1 rounded-xl border border-warning/40 bg-warning-soft px-3 py-2 text-xs text-warning">
              {problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <dl className="divide-y divide-[color:var(--color-line-soft)] rounded-xl border border-line-soft text-sm">
            {[
              ["Funil", flow?.name ?? "—"],
              ["Sócio vendedor", partner?.name ?? "—"],
              ["Gateway", GATEWAY_NAMES[gateway]],
              ...(takeAll
                ? [["Vendas", "100% para você · sócio não é avisado"]]
                : [["Vendedor fica com", pct(s)], ["Sua comissão", pct(o)]]),
              ...(gateway === "snakepay"
                ? [["Seu ShopID", ownerShop.trim() ? `••••${ownerShop.trim().slice(-4)}` : initial?.owner_shop_id ?? (takeAll || o > 0 ? "—" : "não precisa")]]
                : []),
              ["Loop junto", myLoops.find((loop) => loop.id === currentLoop)?.name ?? "Sem loop"],
            ].map(([label, value]) => (
              <div className="flex items-center justify-between gap-3 px-3 py-2" key={label}>
                <dt className="text-muted">{label}</dt>
                <dd className="text-right font-medium text-fg">{value}</dd>
              </div>
            ))}
          </dl>
          {takeAll ? (
            <div className="rounded-xl border border-line-soft bg-surface-inset p-3 text-xs leading-5 text-fg-2">
              <p className="font-semibold text-fg">Como cada venda é cobrada</p>
              <p className="mt-1">
                O Pix é gerado na sua conta {GATEWAY_NAMES[gateway]} e o líquido inteiro fica com você. O sócio não recebe nada, não é avisado e
                não vê essas vendas, os leads nem o faturamento delas.
              </p>
            </div>
          ) : (
          <div className="rounded-xl border border-line-soft bg-surface-inset p-3 text-xs leading-5 text-fg-2">
            <p className="font-semibold text-fg">Como cada venda é dividida</p>
            <p className="mt-1">
              Base de cálculo: o valor líquido da venda (bruto menos a taxa do gateway). Sua comissão sai dessa base pelo split do gateway, na
              hora da cobrança. A taxa Flash por venda sai da parte do vendedor. Venda estornada não gera comissão.
            </p>
            {gateway === "snakepay" && !Number.isNaN(o) && (
              <p className="mt-2">
                Exemplo, venda de {brl(100)}: taxa SnakePay {brl(100 - exampleNet)} → líquido {brl(exampleNet)}; você recebe{" "}
                {brl(Math.floor(exampleNet * o) / 100)} e o vendedor até {brl(Math.floor(exampleNet * s) / 100)}.
              </p>
            )}
            {gateway === "smokepay" && <p className="mt-2">A taxa da SmokePay segue o contrato da conta; o painel mostra a taxa real de cada venda.</p>}
          </div>
          )}
          <p className="flex items-center gap-1.5 text-xs text-muted">
            <Check className="text-success" size={14} /> As regras valem para as próximas vendas; as já feitas mantêm as regras com que foram cobradas.
          </p>
          {save.error && <ErrorState message={errorText(save.error)} />}
        </div>
      )}
    </Modal>
  );
}

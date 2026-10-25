import { useState } from "react";
import { Check, Shield, X } from "lucide-react";
import { usePartnerPermissions, useUpdatePartnerPermissions } from "@/features/partners/permissionsApi";
import type { PartnerPermissions, PlatformType } from "@/types/permissions";
import { LoadingState, ErrorState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";

interface PermissionToggleProps {
  label: string;
  description: string;
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
}

function PermissionToggle({ label, description, enabled, onChange, disabled }: PermissionToggleProps) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-line-soft bg-surface-inset p-3">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-fg">{label}</p>
        <p className="mt-1 text-xs text-muted">{description}</p>
      </div>
      <button
        className={`flex h-8 w-14 shrink-0 items-center rounded-full transition-colors ${
          enabled ? "bg-success" : "bg-line"
        } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
        disabled={disabled}
        onClick={() => onChange(!enabled)}
        type="button"
      >
        <span
          className={`flex h-6 w-6 items-center justify-center rounded-full bg-white shadow-sm transition-transform ${
            enabled ? "translate-x-[34px]" : "translate-x-1"
          }`}
        >
          {enabled ? <Check className="text-success" size={14} /> : <X className="text-muted" size={14} />}
        </span>
      </button>
    </div>
  );
}

interface PartnerPermissionsManagerProps {
  userId: string;
  userName: string;
  open: boolean;
  onClose: () => void;
}

export function PartnerPermissionsManager({ userId, userName, open, onClose }: PartnerPermissionsManagerProps) {
  const [platform, setPlatform] = useState<PlatformType>("flashpost");
  const permissions = usePartnerPermissions(userId);
  const updatePermissions = useUpdatePartnerPermissions();

  const currentPerms = permissions.data?.[platform];
  const [localPerms, setLocalPerms] = useState<Partial<PartnerPermissions>>({});

  const handleToggle = (key: keyof PartnerPermissions, value: boolean) => {
    setLocalPerms((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    if (!currentPerms) return;

    const updates = { ...currentPerms, ...localPerms };
    await updatePermissions.mutateAsync({ userId, platform, permissions: updates });
    setLocalPerms({});
  };

  const getPermValue = (key: keyof PartnerPermissions): boolean => {
    if (key in localPerms) return localPerms[key] as boolean;
    return currentPerms?.[key] ?? false;
  };

  const hasChanges = Object.keys(localPerms).length > 0;

  if (!open) return null;

  return (
    <Modal onClose={onClose} open={open} title={`Permissões de ${userName}`}>
      <div className="space-y-4">
        <div className="flex items-center gap-2 rounded-lg border border-line-soft bg-surface-inset p-3">
          <Shield className="text-accent" size={18} />
          <p className="text-xs text-muted">
            Configure individualmente quais abas e funcionalidades {userName} pode acessar em cada plataforma.
          </p>
        </div>

        <div className="flex gap-2">
          <button
            className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              platform === "flashpost"
                ? "bg-accent text-white"
                : "bg-surface-inset text-muted hover:bg-surface-hover"
            }`}
            onClick={() => setPlatform("flashpost")}
            type="button"
          >
            Flash Post
          </button>
          <button
            className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              platform === "flashbot"
                ? "bg-accent text-white"
                : "bg-surface-inset text-muted hover:bg-surface-hover"
            }`}
            onClick={() => setPlatform("flashbot")}
            type="button"
          >
            Flash Bot
          </button>
        </div>

        {permissions.isLoading && <LoadingState label="Carregando permissões" />}
        {permissions.error && (
          <ErrorState message="Não foi possível carregar as permissões." onRetry={() => void permissions.refetch()} />
        )}

        {permissions.data && currentPerms && (
          <div className="space-y-2">
            {platform === "flashpost" && (
              <>
                <PermissionToggle
                  description="Visualizar o painel principal com indicadores"
                  enabled={getPermValue("can_view_dashboard")}
                  label="Painel"
                  onChange={(v) => handleToggle("can_view_dashboard", v)}
                />
                <PermissionToggle
                  description="Acessar o ranking diário de visualizações"
                  enabled={getPermValue("can_view_ranking")}
                  label="Ranking"
                  onChange={(v) => handleToggle("can_view_ranking", v)}
                />
                <PermissionToggle
                  description="Gerenciar contas conectadas do Instagram"
                  enabled={getPermValue("can_view_accounts")}
                  label="Contas Conectadas"
                  onChange={(v) => handleToggle("can_view_accounts", v)}
                />
                <PermissionToggle
                  description="Configurar aplicativos Meta (Facebook)"
                  enabled={getPermValue("can_view_meta_apps")}
                  label="Apps Meta"
                  onChange={(v) => handleToggle("can_view_meta_apps", v)}
                />
                <PermissionToggle
                  description="Acessar configurações da plataforma"
                  enabled={getPermValue("can_view_settings")}
                  label="Configurações"
                  onChange={(v) => handleToggle("can_view_settings", v)}
                />
                <PermissionToggle
                  description="Visualizar informações de contato"
                  enabled={getPermValue("can_view_contact")}
                  label="Contato"
                  onChange={(v) => handleToggle("can_view_contact", v)}
                />
              </>
            )}

            {platform === "flashbot" && (
              <>
                <PermissionToggle
                  description="Visualizar o painel principal do Flash Bot"
                  enabled={getPermValue("can_view_bot_dashboard")}
                  label="Painel"
                  onChange={(v) => handleToggle("can_view_bot_dashboard", v)}
                />
                <PermissionToggle
                  description="Acessar e gerenciar leads"
                  enabled={getPermValue("can_view_leads")}
                  label="Leads"
                  onChange={(v) => handleToggle("can_view_leads", v)}
                />
                <PermissionToggle
                  description="Visualizar carteiras e sacar valores"
                  enabled={getPermValue("can_view_wallets")}
                  label="Carteiras"
                  onChange={(v) => handleToggle("can_view_wallets", v)}
                />
              </>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 border-t border-line-soft pt-4">
          <button className="btn-secondary" onClick={onClose} type="button">
            Cancelar
          </button>
          <button
            className="btn-primary"
            disabled={!hasChanges || updatePermissions.isPending}
            onClick={() => void handleSave()}
            type="button"
          >
            {updatePermissions.isPending ? "Salvando..." : "Salvar alterações"}
          </button>
        </div>

        {updatePermissions.error && (
          <p className="text-xs text-danger">Erro ao salvar permissões. Tente novamente.</p>
        )}
      </div>
    </Modal>
  );
}

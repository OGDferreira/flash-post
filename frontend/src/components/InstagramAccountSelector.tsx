import { useMemo, useState } from "react";
import { Check, Search } from "lucide-react";

import { InstagramAvatar } from "@/components/InstagramAvatar";
import {
  filterInstagramAccounts,
  toggleAllInstagramAccounts,
  toggleInstagramAccountSelection,
} from "@/features/analytics/filterInstagramAccounts";

export type InstagramAccountOption = {
  id: string;
  username: string;
  profile_picture_url: string | null;
};

type InstagramAccountSelectorProps = {
  accounts: InstagramAccountOption[];
  selectedAccountIds: string[];
  onSelectionChange: (ids: string[]) => void;
  selectionMode?: "multiple" | "single";
  label?: string;
};

export function InstagramAccountSelector({
  accounts,
  selectedAccountIds,
  onSelectionChange,
  selectionMode = "multiple",
  label = "Contas conectadas",
}: InstagramAccountSelectorProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const visibleAccounts = useMemo(
    () => filterInstagramAccounts(accounts, searchTerm),
    [accounts, searchTerm],
  );
  const allSelected =
    accounts.length > 0 && accounts.every((account) => selectedAccountIds.includes(account.id));

  function toggleAccount(accountId: string) {
    if (selectionMode === "single") {
      onSelectionChange([accountId]);
      return;
    }
    onSelectionChange(toggleInstagramAccountSelection(selectedAccountIds, accountId));
  }

  return (
    <section className="rounded-xl border border-[#202838] bg-[#0d1015] p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-medium text-[#e6eaf2]">{label}</h2>
        {selectionMode === "multiple" && accounts.length > 0 && (
          <button
            className="text-xs text-[#aab7ff] hover:text-white"
            type="button"
            onClick={() =>
              onSelectionChange(
                toggleAllInstagramAccounts(
                  accounts.map(({ id }) => id),
                  selectedAccountIds,
                ),
              )
            }
          >
            {allSelected ? "Limpar seleção" : "Selecionar todas"}
          </button>
        )}
      </div>
      <label className="mt-3 flex min-h-10 items-center gap-2 rounded-lg border border-[#27334a] bg-[#090b0f] px-3 text-[#94a3b8]">
        <Search size={15} />
        <input
          aria-label="Buscar conta conectada"
          className="w-full bg-transparent text-sm text-[#f5f7fb] outline-none placeholder:text-[#64748b]"
          placeholder="Buscar por @usuário..."
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
        />
      </label>
      <div className="mt-3 max-h-72 space-y-1 overflow-y-auto">
        {visibleAccounts.map((account) => {
          const selected = selectedAccountIds.includes(account.id);
          return (
            <button
              aria-pressed={selected}
              className={`flex min-h-12 w-full items-center gap-3 rounded-lg px-2.5 text-left transition ${
                selected
                  ? "bg-[#151b2d] text-white"
                  : "text-[#aeb9ce] hover:bg-[#12151b] hover:text-white"
              }`}
              key={account.id}
              type="button"
              onClick={() => toggleAccount(account.id)}
            >
              <InstagramAvatar
                className="size-8 rounded-full object-cover"
                src={account.profile_picture_url}
                username={account.username}
              />
              <span className="min-w-0 flex-1 truncate text-sm">@{account.username}</span>
              {selected && <Check className="text-[#8295ff]" size={16} />}
            </button>
          );
        })}
        {visibleAccounts.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-[#64748b]">
            {accounts.length ? "Nenhuma conta corresponde à busca." : "Nenhuma conta conectada."}
          </p>
        )}
      </div>
      {selectionMode === "multiple" && (
        <p className="mt-2 text-xs text-[#64748b]">
          {selectedAccountIds.length} de {accounts.length} selecionada(s)
        </p>
      )}
    </section>
  );
}

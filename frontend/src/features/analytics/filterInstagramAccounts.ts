export function filterInstagramAccounts<T extends { username: string }>(
  accounts: T[],
  searchTerm: string,
): T[] {
  const normalized = searchTerm.trim().replace(/^@/, "").toLowerCase();
  if (!normalized) return accounts;
  return accounts.filter((account) => account.username.toLowerCase().includes(normalized));
}

export function toggleInstagramAccountSelection(
  selectedIds: string[],
  accountId: string,
): string[] {
  return selectedIds.includes(accountId)
    ? selectedIds.filter((id) => id !== accountId)
    : [...selectedIds, accountId];
}

export function toggleAllInstagramAccounts(
  accountIds: string[],
  selectedIds: string[],
): string[] {
  return accountIds.length > 0 && accountIds.every((id) => selectedIds.includes(id))
    ? []
    : accountIds;
}

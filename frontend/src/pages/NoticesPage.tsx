import { AlertTriangle, Bell } from "lucide-react";

import { EmptyState } from "@/components/PageState";
import { useShellContext } from "@/layouts/shellContext";

/** Avisos: the notices that used to sit behind the bell in the top bar. */
export function NoticesPage() {
  const { notificationItems } = useShellContext();
  return (
    <div className="mx-auto max-w-[760px] space-y-4">
      <h1 className="flex items-center gap-2 text-2xl font-semibold text-fg">
        <Bell className="text-accent" size={22} /> Avisos
      </h1>
      {notificationItems.length === 0 ? (
        <EmptyState message="Nenhum aviso no momento." />
      ) : (
        <ul className="glass-panel divide-y divide-line-soft p-2">
          {notificationItems.map((item, index) => (
            <li className="flex gap-3 px-2 py-3" key={`${item.title}-${index}`}>
              <AlertTriangle aria-hidden="true" className="mt-0.5 shrink-0 text-warning" size={16} />
              <div>
                <h2 className="text-sm font-medium text-fg">{item.title}</h2>
                <p className="mt-1 text-sm leading-5 text-fg-2">{item.message}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

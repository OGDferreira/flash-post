import { CircleAlert, LoaderCircle } from "lucide-react";

export function LoadingState({ label = "Carregando" }: { label?: string }) {
  return (
    <div className="flex min-h-48 items-center justify-center gap-3 text-sm text-[#94a3b8]">
      <LoaderCircle className="animate-spin text-[#7186ff]" size={18} />
      {label}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-[#47252d] bg-[#1a1013] p-4 text-sm text-[#f1a3ad]">
      <CircleAlert size={17} />
      {message}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-dashed border-[#27334a] px-5 py-10 text-center text-sm text-[#94a3b8]">
      {message}
    </div>
  );
}

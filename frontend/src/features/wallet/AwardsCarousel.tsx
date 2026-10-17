import { useRef } from "react";
import { ChevronLeft, ChevronRight, Gift, Lock, Trophy } from "lucide-react";

import { brl, compact, type GoalItem } from "@/features/wallet/api";

/** SharkBot-style awards: one card per goal, photo set by the Super Admin, lock until reached. */
export function AwardsCarousel({ goals, revenue }: { goals: GoalItem[]; revenue: number }) {
  const track = useRef<HTMLDivElement>(null);
  const scroll = (direction: number) => track.current?.scrollBy({ left: direction * 260, behavior: "smooth" });
  return (
    <div className="relative">
      <div className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2 [scrollbar-width:none]" ref={track}>
        {goals.map((goal) => {
          const locked = !goal.reached && !goal.current;
          const percent = Math.min(100, (revenue / goal.amount) * 100);
          return (
            <article
              className={`relative w-[220px] shrink-0 snap-start overflow-hidden rounded-2xl border bg-surface-inset ${goal.current ? "border-accent shadow-[0_0_24px_-8px_var(--color-accent)]" : goal.reached ? "border-success/50" : "border-line-soft"}`}
              key={goal.amount}
            >
              <div className="relative aspect-square overflow-hidden bg-well">
                {goal.image_url ? (
                  <img alt={goal.prize} className={`h-full w-full object-cover transition duration-500 ${locked ? "scale-105 blur-[2px] brightness-[.35] grayscale" : ""}`} loading="lazy" src={goal.image_url} />
                ) : (
                  <div className={`flex h-full w-full items-center justify-center ${locked ? "opacity-30" : ""}`}>
                    <Trophy className="text-warning" size={56} />
                  </div>
                )}
                {locked && (
                  <span className="absolute inset-0 flex items-center justify-center">
                    <span className="rounded-full bg-black/60 p-3 text-white"><Lock size={22} /></span>
                  </span>
                )}
                {goal.current && <span className="absolute left-2 top-2 rounded-md bg-accent px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">Atual</span>}
                {goal.reached && <span className="absolute left-2 top-2 rounded-md bg-success px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">Conquistada</span>}
              </div>
              <div className="space-y-1.5 p-3">
                <p className="flex items-center gap-1 text-xs font-semibold text-fg"><Gift size={13} className="text-warning" /> {goal.prize}</p>
                <p className="text-[11px] text-muted">{goal.reached ? `Meta de ${compact(goal.amount)} batida` : `${brl(Math.min(revenue, goal.amount))} / ${brl(goal.amount)}`}</p>
                <div className="h-1.5 overflow-hidden rounded-full bg-well">
                  <div className={`h-full rounded-full ${goal.reached ? "bg-success" : "bg-accent"}`} style={{ width: `${percent}%` }} />
                </div>
              </div>
            </article>
          );
        })}
      </div>
      <button aria-label="Anterior" className="absolute left-1 top-[40%] hidden rounded-full bg-black/60 p-1.5 text-white sm:block" onClick={() => scroll(-1)} type="button"><ChevronLeft size={18} /></button>
      <button aria-label="Próxima" className="absolute right-1 top-[40%] hidden rounded-full bg-black/60 p-1.5 text-white sm:block" onClick={() => scroll(1)} type="button"><ChevronRight size={18} /></button>
    </div>
  );
}

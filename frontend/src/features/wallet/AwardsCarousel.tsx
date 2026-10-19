import { useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Lock, Trophy } from "lucide-react";

import { awardTitle, awardUnlocked, brl, compact, type GoalItem } from "@/features/wallet/api";

/** SharkBot-style awards: one card per goal, photo set by the Super Admin, locked until the goal is reached. */
export function AwardsCarousel({ goals, revenue }: { goals: GoalItem[]; revenue: number }) {
  const track = useRef<HTMLDivElement>(null);
  const scroll = (direction: number) => track.current?.scrollBy({ left: direction * 260, behavior: "smooth" });
  // Mouse drag with a little momentum (fingers already scroll natively); snapping is paused
  // while dragging and comes back on release, so the row settles smoothly on a card.
  const drag = useRef<{ x: number; left: number; lastX: number; lastT: number; v: number; moved: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);
  const onPointerDown = (event: React.PointerEvent) => {
    if (event.pointerType !== "mouse" || !track.current) return;
    drag.current = { x: event.clientX, left: track.current.scrollLeft, lastX: event.clientX, lastT: performance.now(), v: 0, moved: false };
  };
  const onPointerMove = (event: React.PointerEvent) => {
    const state = drag.current;
    if (!state || !track.current) return;
    const dx = event.clientX - state.x;
    if (!state.moved && Math.abs(dx) > 5) {
      state.moved = true;
      setDragging(true);
      track.current.setPointerCapture(event.pointerId);
    }
    if (!state.moved) return;
    const now = performance.now();
    state.v = (event.clientX - state.lastX) / Math.max(1, now - state.lastT);
    state.lastX = event.clientX;
    state.lastT = now;
    track.current.scrollLeft = state.left - dx;
  };
  const onPointerUp = () => {
    const state = drag.current;
    drag.current = null;
    if (!state?.moved || !track.current) return;
    setDragging(false);
    track.current.scrollBy({ left: -state.v * 220, behavior: "smooth" });
  };
  return (
    <div className="relative">
      <div
        className={`flex gap-3 overflow-x-auto scroll-smooth pb-2 [scrollbar-width:none] ${dragging ? "cursor-grabbing select-none [scroll-behavior:auto]" : "cursor-grab snap-x snap-mandatory"}`}
        onPointerCancel={onPointerUp}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        ref={track}
      >
        {goals.map((goal) => {
          const locked = !awardUnlocked(goal);
          const percent = Math.min(100, (revenue / goal.amount) * 100);
          return (
            <article
              className={`group relative w-[220px] shrink-0 snap-start overflow-hidden rounded-2xl border bg-surface-inset transition-transform duration-300 ease-out hover:-translate-y-1 ${goal.current ? "border-accent/60" : goal.reached ? "border-success/50" : "border-line-soft"}`}
              key={goal.amount}
            >
              <div className="relative aspect-[4/5] overflow-hidden bg-well">
                {goal.image_url ? (
                  <img
                    draggable={false}
                    alt={awardTitle(goal.amount)}
                    className={`h-full w-full object-cover transition-[filter,transform] duration-700 ease-out ${
                      locked
                        ? "scale-105 blur-[2px] brightness-[.35] grayscale group-hover:scale-100 group-hover:blur-[0px] group-hover:brightness-[.7] group-hover:grayscale-[.6]"
                        : "group-hover:scale-[1.03]"
                    }`}
                    loading="lazy"
                    src={goal.image_url}
                  />
                ) : (
                  <div className={`flex h-full w-full items-center justify-center ${locked ? "opacity-30" : ""}`}>
                    <Trophy className="text-warning" size={56} />
                  </div>
                )}
                {locked && (
                  <span className="pointer-events-none absolute inset-0 flex items-center justify-center transition-transform duration-700 ease-out group-hover:-translate-y-[38%]">
                    <span className="rounded-full bg-black/60 p-3 text-white transition-transform duration-700 group-hover:scale-75"><Lock size={22} /></span>
                  </span>
                )}
                {goal.current && <span className="absolute left-2 top-2 flex items-center gap-1 rounded-md bg-black/70 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white"><Lock size={10} /> Próxima meta</span>}
                {goal.reached && <span className="absolute left-2 top-2 rounded-md bg-success px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">Conquistada</span>}
              </div>
              <div className="space-y-1.5 p-3">
                <p className="flex items-center gap-1 text-xs font-semibold text-fg">
                  {locked ? <Lock size={13} className="text-muted" /> : <Trophy size={13} className="text-warning" />} {awardTitle(goal.amount)} faturados
                </p>
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

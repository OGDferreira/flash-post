import { useRef, useState, type ReactNode } from "react";
import { GripVertical } from "lucide-react";

/**
 * Press, hold and drag the handle to reorder (mouse and touch). Pointer events with capture,
 * so it works the same on a phone; the list reorders live while dragging.
 */
export function SortableList<T>({
  items,
  getKey,
  onReorder,
  onDragStart,
  render,
}: {
  items: T[];
  getKey: (item: T) => string;
  onReorder: (next: T[]) => void;
  onDragStart?: () => void;
  render: (item: T, index: number, handle: ReactNode) => ReactNode;
}) {
  const rows = useRef(new Map<string, HTMLDivElement>());
  const [dragging, setDragging] = useState<string | null>(null);

  const move = (key: string, clientY: number) => {
    const from = items.findIndex((item) => getKey(item) === key);
    if (from < 0) return;
    // New place = how many of the other rows have their middle above the pointer.
    let to = 0;
    items.forEach((item) => {
      const itemKey = getKey(item);
      if (itemKey === key) return;
      const box = rows.current.get(itemKey)?.getBoundingClientRect();
      if (box && clientY > box.top + box.height / 2) to += 1;
    });
    if (to === from) return;
    const next = [...items];
    const [picked] = next.splice(from, 1);
    next.splice(to, 0, picked);
    onReorder(next);
  };

  return (
    <div className="space-y-2">
      {items.map((item, index) => {
        const key = getKey(item);
        const handle = (
          <button
            aria-label="Segure e arraste para mudar a ordem"
            className="grid min-h-9 cursor-grab touch-none place-items-center rounded-lg px-1.5 text-muted hover:bg-well hover:text-fg active:cursor-grabbing"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              // Keyboard: arrows move the item one place.
              const step = event.key === "ArrowUp" ? -1 : event.key === "ArrowDown" ? 1 : 0;
              const to = index + step;
              if (!step || to < 0 || to >= items.length) return;
              event.preventDefault();
              const next = [...items];
              [next[index], next[to]] = [next[to], next[index]];
              onReorder(next);
            }}
            onPointerDown={(event) => {
              event.stopPropagation();
              event.currentTarget.setPointerCapture(event.pointerId);
              setDragging(key);
              onDragStart?.();
            }}
            onPointerMove={(event) => {
              if (dragging === key) move(key, event.clientY);
            }}
            onPointerUp={() => setDragging(null)}
            onPointerCancel={() => setDragging(null)}
            title="Segure e arraste para mudar a ordem"
            type="button"
          >
            <GripVertical size={16} />
          </button>
        );
        return (
          <div
            className={`transition-shadow ${dragging === key ? "relative z-10 rounded-xl opacity-90 shadow-lg ring-2 ring-brand" : ""}`}
            key={key}
            ref={(node) => {
              if (node) rows.current.set(key, node);
              else rows.current.delete(key);
            }}
          >
            {render(item, index, handle)}
          </div>
        );
      })}
    </div>
  );
}

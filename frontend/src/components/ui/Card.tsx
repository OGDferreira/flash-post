import type { HTMLAttributes } from "react";

type CardProps = HTMLAttributes<HTMLElement> & {
  /** raised = plate lifted off the page, inset = pressed-in well. */
  tone?: "raised" | "inset";
  as?: "section" | "article" | "div";
};

export function Card({ tone = "raised", as: Tag = "section", className = "", ...props }: CardProps) {
  return (
    <Tag
      className={`rounded-2xl border border-line p-4 ${tone === "raised" ? "bg-surface" : "bg-surface-inset"} ${className}`.trim()}
      {...props}
    />
  );
}

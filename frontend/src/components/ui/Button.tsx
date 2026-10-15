import type { ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
};

/** Single button primitive: the look lives in the .btn-* classes (index.css). */
export function Button({ variant = "secondary", size = "md", className = "", type = "button", ...props }: ButtonProps) {
  return (
    <button
      className={`btn-${variant === "danger" ? "secondary btn-danger" : variant} ${size === "sm" ? "btn-sm" : ""} ${className}`.trim()}
      type={type}
      {...props}
    />
  );
}

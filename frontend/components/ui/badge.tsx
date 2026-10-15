import type { ReactNode } from "react";

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "healthy" | "pending" | "danger" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}


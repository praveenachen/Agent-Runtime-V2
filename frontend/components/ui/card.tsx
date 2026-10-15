import type { ReactNode } from "react";

export function Card({ title, eyebrow, children }: { title: string; eyebrow?: string; children: ReactNode }) {
  return (
    <article className="card">
      <header>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2></header>
      {children}
    </article>
  );
}


import Link from "next/link";
import type { ReactNode } from "react";

const navigation = [
  ["Overview", "/"],
  ["Runs", "/runs"],
  ["Policies", "/policies"],
  ["Approvals", "/approvals"],
  ["Compare", "/compare"],
  ["Settings", "/settings"],
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="Agent Runtime home">
          <span className="brand-mark">AR</span>
          <span><strong>Agent Runtime</strong><small>Debug the decisions</small></span>
        </Link>
        <nav aria-label="Primary navigation">
          {navigation.map(([label, href]) => <Link href={href} key={href}>{label}</Link>)}
        </nav>
        <div className="sidebar-footer"><span className="health-dot" /> Local development</div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <button className="project-select" type="button">Default project <span>⌄</span></button>
          <div className="topbar-actions">
            <button aria-label="Search" type="button">⌘ K</button>
            <button aria-label="Notifications" type="button">0 alerts</button>
            <span className="avatar" aria-label="Local developer">LD</span>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}


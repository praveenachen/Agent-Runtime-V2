"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Icon, type IconName } from "@/components/ui/icon";
import { fetchApprovals, type Approval } from "@/lib/api";
import { APPROVAL_CHANGED_EVENT, useProjectId } from "@/lib/project";

const navigation: Array<[string, string, IconName]> = [
  ["Overview", "/", "overview"], ["Runs", "/runs", "runs"],
  ["Policies", "/policies", "policy"], ["Approvals", "/approvals", "approval"],
  ["Compare", "/compare", "compare"], ["Settings", "/settings", "settings"],
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { projectId } = useProjectId();
  const [approvalState, setApprovalState] = useState<{ projectId: string; items: Approval[] }>({ projectId: "", items: [] });
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const approvals = approvalState.projectId === projectId ? approvalState.items : [];

  useEffect(() => {
    if (!projectId) return;
    const controller = new AbortController();
    const refresh = () => fetchApprovals(projectId, controller.signal).then((items) => setApprovalState({ projectId, items })).catch((error: Error) => {
      if (error.name !== "AbortError") setApprovalState({ projectId, items: [] });
    });
    refresh();
    window.addEventListener(APPROVAL_CHANGED_EVENT, refresh);
    return () => { controller.abort(); window.removeEventListener(APPROVAL_CHANGED_EVENT, refresh); };
  }, [projectId]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="Agent Runtime home"><span className="brand-mark"><Icon name="graph" /></span><span><strong>Agent Runtime</strong><small>Debug the decisions</small></span></Link>
        <nav aria-label="Primary navigation">{navigation.map(([label, href, icon]) => <Link className={pathname === href || (href !== "/" && pathname.startsWith(href)) ? "active" : ""} href={href} key={href}><Icon name={icon} /><span>{label}</span>{label === "Approvals" && approvals.length > 0 && <b className="nav-count">{approvals.length}</b>}</Link>)}</nav>
        <div className="sidebar-footer"><span className="health-dot" /> Local development</div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <Link className="project-select" href="/policies"><Icon name="shield" /><span>{projectId ? `Project ${projectId.slice(0, 8)}` : "Select project"}</span><small>Control scope</small></Link>
          <div className="topbar-actions">
            <Link className="search-trigger" href="/runs" aria-label="Search runs"><Icon name="search" /><span>Search runs</span><kbd>⌘ K</kbd></Link>
            <div className="notification-wrap">
              <button className={approvals.length ? "notification-button notification-active" : "notification-button"} aria-expanded={notificationsOpen} aria-haspopup="dialog" aria-label={`${approvals.length} actionable notifications`} onClick={() => setNotificationsOpen((open) => !open)} type="button"><Icon name="bell" />{approvals.length > 0 && <b>{approvals.length}</b>}</button>
              {notificationsOpen && <div className="notification-menu" role="dialog" aria-label="Actionable notifications">
                <header><div><strong>Action required</strong><small>Runtime control events only</small></div><button aria-label="Close notifications" onClick={() => setNotificationsOpen(false)} type="button"><Icon name="x" /></button></header>
                {approvals.length === 0 ? <div className="notification-empty"><Icon name="check" /><span><strong>You’re all caught up</strong><small>No pending approvals.</small></span></div> : <div className="notification-list">{approvals.slice(0, 4).map((approval) => <Link href="/approvals" key={approval.id} onClick={() => setNotificationsOpen(false)}><span className="notification-risk"><Icon name="alert" /></span><span><strong>{approval.action_summary}</strong><small>{approval.agent_name ?? "Unknown agent"} · {approval.operation ?? "Action review"}</small></span><Icon name="arrow" /></Link>)}</div>}
                <Link className="notification-footer" href="/approvals" onClick={() => setNotificationsOpen(false)}>Open approval inbox <Icon name="arrow" /></Link>
              </div>}
            </div>
            <span className="avatar" aria-label="Local developer">LD</span>
          </div>
        </header>
        <div id="main-content">{children}</div>
      </div>
    </div>
  );
}

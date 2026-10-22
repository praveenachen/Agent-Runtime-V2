"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Icon, type IconName } from "@/components/ui/icon";
import { fetchApprovals, type Approval } from "@/lib/api";
import { APPROVAL_CHANGED_EVENT, useProjectDiscovery } from "@/lib/project";

const navigation: Array<[string, string, IconName]> = [
  ["Overview", "/", "overview"], ["Runs", "/runs", "runs"],
  ["Policies", "/policies", "policy"], ["Approvals", "/approvals", "approval"],
  ["Compare", "/compare", "compare"],
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { projectId, setProjectId, projects, runs: allRuns, loading: projectsLoading } = useProjectDiscovery();
  const [approvalState, setApprovalState] = useState<{ projectId: string; items: Approval[] }>({ projectId: "", items: [] });
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const [projectDraft, setProjectDraft] = useState("");
  const approvals = approvalState.projectId === projectId ? approvalState.items : [];
  const projectLabel = projects.find((project) => project.id === projectId)?.label ?? (projectId ? `Project ${projectId.slice(0, 8)}` : projectsLoading ? "Finding projects…" : "Select project");
  const recordedRuns = allRuns?.length ?? 0;
  const toggleProjectMenu = () => { setProjectDraft(projectId); setProjectMenuOpen((open) => !open); };

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
        <Link className="brand" href="/" aria-label="Agent Runtime home"><span className="brand-mark"><BrandLogo /></span><span><strong>Agent Runtime</strong><small>Debug the decisions</small></span></Link>
        <nav aria-label="Primary navigation">{navigation.map(([label, href, icon]) => <Link className={pathname === href || (href !== "/" && pathname.startsWith(href)) ? "active" : ""} href={href} key={href}><Icon name={icon} /><span>{label}</span>{label === "Approvals" && approvals.length > 0 && <b className="nav-count">{approvals.length}</b>}</Link>)}</nav>
        <div className="sidebar-bottom">
          <section className="sidebar-project" aria-label="Project">
            <p className="sidebar-section-label">Project</p>
            <button className="sidebar-link" onClick={toggleProjectMenu} type="button"><Icon name="building" /><span>{projectLabel}</span><Icon className="trail" name="chevron" /></button>
            <a className="sidebar-link" href="https://github.com/praveenachen/Agent-Runtime-V2/tree/main/docs" rel="noreferrer" target="_blank"><Icon name="book" /><span>Documentation</span><Icon className="trail" name="external" /></a>
            <a className="sidebar-link" href="https://github.com/praveenachen/Agent-Runtime-V2/issues" rel="noreferrer" target="_blank"><Icon name="help" /><span>Get Help</span><Icon className="trail" name="external" /></a>
          </section>
          <section className="plan-card" aria-label="Local usage">
            <p><span className="health-dot" />Local development</p>
            <strong>{recordedRuns.toLocaleString()} <small>recorded run{recordedRuns === 1 ? "" : "s"}</small></strong>
            <div className="plan-bar" aria-hidden="true"><i /></div>
            <Link href="/runs">View runs <Icon name="arrow" /></Link>
          </section>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="project-switcher">
            <button className="project-select" aria-expanded={projectMenuOpen} aria-haspopup="dialog" onClick={toggleProjectMenu} title={projectId ? "Recorded telemetry scope" : "Choose recorded telemetry"} type="button"><Icon name="building" /><span>{projectLabel}</span><Icon className="chevron" name="chevron" /></button>
            {projectMenuOpen && <form className="project-menu" onSubmit={(event) => { event.preventDefault(); if (!projectDraft.trim()) return; setProjectId(projectDraft); setProjectMenuOpen(false); }}>
              <label htmlFor="global-project-id"><strong>Project scope</strong><small>Discovered from real runs and used by Overview, Policies, and Approvals.</small></label>
              {projects.length > 0 && <select className="project-menu-select" aria-label="Recorded project" onChange={(event) => setProjectDraft(event.target.value)} value={projects.some((project) => project.id === projectDraft) ? projectDraft : ""}><option value="">Select recorded project</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.label} · {project.runCount} run{project.runCount === 1 ? "" : "s"}</option>)}</select>}
              <details className="manual-project"><summary>Advanced: enter project UUID</summary><input autoFocus={projects.length === 0} id="global-project-id" onChange={(event) => setProjectDraft(event.target.value)} placeholder="Project UUID" value={projectDraft} /></details>
              <div><button className="button-ghost" onClick={() => setProjectMenuOpen(false)} type="button">Cancel</button><button className="button-secondary" disabled={!projectDraft.trim()} type="submit">Use project</button></div>
            </form>}
          </div>
          <div className="topbar-actions">
            <Link className="search-trigger" href="/runs" aria-label="Search runs"><Icon name="search" /><span>Search runs, agents, tools, or traces...</span><kbd>⌘ K</kbd></Link>
            <div className="notification-wrap">
              <button className={approvals.length ? "notification-button notification-active" : "notification-button"} aria-expanded={notificationsOpen} aria-haspopup="dialog" aria-label={`${approvals.length} actionable notifications`} onClick={() => setNotificationsOpen((open) => !open)} type="button"><Icon name="bell" />{approvals.length > 0 && <b>{approvals.length}</b>}</button>
              {notificationsOpen && <div className="notification-menu" role="dialog" aria-label="Actionable notifications">
                <header><div><strong>Action required</strong><small>Runtime control events only</small></div><button aria-label="Close notifications" onClick={() => setNotificationsOpen(false)} type="button"><Icon name="x" /></button></header>
                {approvals.length === 0 ? <div className="notification-empty"><Icon name="check" /><span><strong>You’re all caught up</strong><small>No pending approvals.</small></span></div> : <div className="notification-list">{approvals.slice(0, 4).map((approval) => <Link href="/approvals" key={approval.id} onClick={() => setNotificationsOpen(false)}><span className="notification-risk"><Icon name="alert" /></span><span><strong>{approval.action_summary}</strong><small>{approval.agent_name ?? "Unknown agent"} · {approval.operation ?? "Action review"}</small></span><Icon name="arrow" /></Link>)}</div>}
                <Link className="notification-footer" href="/approvals" onClick={() => setNotificationsOpen(false)}>Open approval inbox <Icon name="arrow" /></Link>
              </div>}
            </div>
            <button className="user-menu" type="button" aria-label="Local Developer, Local workspace"><span className="avatar" aria-hidden="true">LD</span><span className="user-meta"><strong>Local Developer</strong><small>Local workspace</small></span><Icon className="chevron" name="chevron" /></button>
          </div>
        </header>
        <div id="main-content">{children}</div>
      </div>
    </div>
  );
}

function BrandLogo() {
  return <svg aria-hidden="true" viewBox="0 0 32 32" fill="none"><defs><linearGradient id="brand-grad" x1="4" y1="28" x2="28" y2="4" gradientUnits="userSpaceOnUse"><stop stopColor="#1f6fe5" /><stop offset="1" stopColor="#5fc2ff" /></linearGradient></defs><path d="M16 3 4.5 27h6.2L16 15.2 21.3 27h6.2L16 3Z" fill="url(#brand-grad)" /><path d="M11.2 24.2h9.6" stroke="#0a1b33" strokeWidth="2.4" strokeLinecap="round" /></svg>;
}

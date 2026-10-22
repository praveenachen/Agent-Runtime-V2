"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApprovalsPanel } from "@/components/approvals-workspace";
import { PoliciesPanel } from "@/components/policies-workspace";
import { Icon } from "@/components/ui/icon";
import { fetchApprovals, fetchPolicies, type Approval, type Policy } from "@/lib/api";
import { useProjectId } from "@/lib/project";

export type Notice = { tone: "success" | "error"; text: string } | null;
export type ControlTab = "approvals" | "policies";
type Loaded = { projectId: string; approvals: Approval[]; policies: Policy[] };

export function ControlWorkspace({ tab }: { tab: ControlTab }) {
  const { projectId } = useProjectId();
  const [data, setData] = useState<Loaded | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [newPolicySignal, setNewPolicySignal] = useState(0);
  const loaded = data && data.projectId === projectId ? data : null;
  const loading = Boolean(projectId) && !loaded;

  useEffect(() => {
    if (!projectId) return;
    const controller = new AbortController();
    Promise.allSettled([fetchApprovals(projectId, controller.signal), fetchPolicies(projectId, controller.signal)]).then(([approvals, policies]) => {
      if (controller.signal.aborted) return;
      setData({ projectId, approvals: approvals.status === "fulfilled" ? approvals.value : [], policies: policies.status === "fulfilled" ? policies.value : [] });
      const failure = [approvals, policies].find((result) => result.status === "rejected");
      if (failure && failure.status === "rejected") setNotice({ tone: "error", text: failure.reason instanceof Error ? failure.reason.message : "Control data could not be loaded." });
    });
    return () => controller.abort();
  }, [projectId]);

  const setApprovals = (update: (items: Approval[]) => Approval[]) => setData((current) => current && { ...current, approvals: update(current.approvals) });
  const setPolicies = (update: (items: Policy[]) => Policy[]) => setData((current) => current && { ...current, policies: update(current.policies) });

  return <main className="page-stack overview-page control-page cw-page">
    <header className="page-heading">
      <div><h1>Approvals &amp; Policies</h1><p className="muted">Review and approve agent actions, and configure policies to control when approvals are required.</p></div>
      {tab === "policies" && projectId && <button className="cw-new-policy" onClick={() => { setNewPolicySignal((value) => value + 1); setNotice(null); }} type="button"><Icon name="spark" /> New policy</button>}
    </header>
    <nav className="cw-tabs" aria-label="Approvals and policies">
      <Link aria-current={tab === "approvals" ? "page" : undefined} className={tab === "approvals" ? "active" : ""} href="/approvals" scroll={false}>Approval inbox{loaded && loaded.approvals.length > 0 && <b>{loaded.approvals.length}</b>}</Link>
      <Link aria-current={tab === "policies" ? "page" : undefined} className={tab === "policies" ? "active" : ""} href="/policies" scroll={false}>Policy library{loaded && <b className="neutral">{loaded.policies.length}</b>}</Link>
    </nav>
    {notice && <div className={`control-message ${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>{notice.text}</div>}
    {!projectId ? <div className="state-panel compact"><span className="state-icon"><Icon name="shield" /></span><h2>Select a project</h2><p>Approvals and policies are isolated by project. Choose one from the project selector in the top bar.</p></div> :
      tab === "approvals" ? <ApprovalsPanel approvals={loaded?.approvals ?? []} loading={loading} notify={setNotice} policies={loaded?.policies ?? []} setApprovals={setApprovals} />
        : <PoliciesPanel loading={loading} newSignal={newPolicySignal} notify={setNotice} policies={loaded?.policies ?? []} projectId={projectId} setPolicies={setPolicies} />}
  </main>;
}

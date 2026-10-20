"use client";

import { useState } from "react";

import { useProjectId } from "@/lib/project";

export function ProjectScope() {
  const { projectId, setProjectId } = useProjectId();
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const startEditing = () => { setDraft(projectId); setEditing(true); };
  if (projectId && !editing) return <div className="project-scope project-scope-active"><div><strong>Project scope</strong><small>Shared across Overview, Policies, and Approvals.</small></div><code title={projectId}>{projectId}</code><button className="button-ghost" onClick={startEditing} type="button">Change</button></div>;
  return <div className="project-scope"><div><strong>Project scope</strong><small>{projectId ? "Choose a different project UUID." : "Select once to use it across runtime control views."}</small></div><input aria-label="Project UUID" autoFocus={editing} onChange={(event) => setDraft(event.target.value)} placeholder="00000000-0000-0000-0000-000000000000" value={draft} /><div className="project-scope-actions">{projectId && <button className="button-ghost" onClick={() => { setDraft(""); setEditing(false); }} type="button">Cancel</button>}<button className="button-secondary" disabled={!draft.trim()} onClick={() => { setProjectId(draft); setDraft(""); setEditing(false); }} type="button">Use project</button></div></div>;
}

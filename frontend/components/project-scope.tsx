"use client";

import { useState } from "react";

import { useProjectDiscovery } from "@/lib/project";

export function ProjectScope() {
  const { projectId, setProjectId, projects, loading, error } = useProjectDiscovery();
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const startEditing = () => { setDraft(projectId); setEditing(true); };
  const selected = projects.find((project) => project.id === projectId);
  if (projectId && !editing) return <div className="project-scope project-scope-active"><div><strong>Project scope</strong><small>Discovered from recorded run telemetry and shared across control views.</small></div><code title={projectId}>{selected?.label ?? `Project ${projectId.slice(0, 8)}`}</code><button className="button-ghost" onClick={startEditing} type="button">Change</button></div>;
  return <div className="project-scope"><div><strong>Project scope</strong><small>{loading ? "Discovering projects from recorded runs…" : error ? "Run discovery is unavailable; enter a UUID manually." : projects.length > 1 ? "Choose a project recorded in telemetry." : "No recorded project was found; enter a UUID manually."}</small></div><div className="project-scope-picker">{projects.length > 0 && <select aria-label="Recorded project" onChange={(event) => setDraft(event.target.value)} value={projects.some((project) => project.id === draft) ? draft : ""}><option value="">Select recorded project</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.label} · {project.runCount} run{project.runCount === 1 ? "" : "s"}</option>)}</select>}<details className="manual-project"><summary>Enter UUID manually</summary><input aria-label="Project UUID" autoFocus={editing && projects.length === 0} onChange={(event) => setDraft(event.target.value)} placeholder="00000000-0000-0000-0000-000000000000" value={draft} /></details></div><div className="project-scope-actions">{projectId && <button className="button-ghost" onClick={() => { setDraft(""); setEditing(false); }} type="button">Cancel</button>}<button className="button-secondary" disabled={!draft.trim()} onClick={() => { setProjectId(draft); setDraft(""); setEditing(false); }} type="button">Use project</button></div></div>;
}

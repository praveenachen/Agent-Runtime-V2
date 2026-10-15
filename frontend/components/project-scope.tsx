"use client";

import { useState } from "react";

import { useProjectId } from "@/lib/project";

export function ProjectScope() {
  const { projectId, setProjectId } = useProjectId();
  const [draft, setDraft] = useState("");
  return <div className="project-scope"><div><strong>Project scope</strong><small>Policies and approvals are isolated by project UUID.</small></div><input aria-label="Project UUID" onChange={(event) => setDraft(event.target.value)} placeholder={projectId || "00000000-0000-0000-0000-000000000000"} value={draft} /><button className="button-secondary" disabled={!draft.trim()} onClick={() => { setProjectId(draft); setDraft(""); }} type="button">Use project</button></div>;
}

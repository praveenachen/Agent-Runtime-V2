"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { fetchRuns, type RunSummary } from "@/lib/api";

export const PROJECT_STORAGE_KEY = "agent-runtime-project-id";
export const PROJECT_CHANGED_EVENT = "agent-runtime-project-changed";
export const APPROVAL_CHANGED_EVENT = "agent-runtime-approval-changed";

export function useProjectId() {
  const projectId = useSyncExternalStore(
    (update) => {
      window.addEventListener(PROJECT_CHANGED_EVENT, update);
      return () => window.removeEventListener(PROJECT_CHANGED_EVENT, update);
    },
    () => window.localStorage.getItem(PROJECT_STORAGE_KEY) ?? "",
    () => "",
  );
  function setProjectId(value: string) {
    const normalized = value.trim();
    window.localStorage.setItem(PROJECT_STORAGE_KEY, normalized);
    window.dispatchEvent(new Event(PROJECT_CHANGED_EVENT));
  }
  return { projectId, setProjectId };
}

export type DiscoveredProject = {
  id: string;
  label: string;
  runCount: number;
};

export function useProjectDiscovery() {
  const { projectId, setProjectId } = useProjectId();
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetchRuns(controller.signal)
      .then((items) => { setRuns(items); setError(""); })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      });
    return () => controller.abort();
  }, []);

  const projects = useMemo(() => discoverProjects(runs ?? []), [runs]);

  useEffect(() => {
    if (!projectId && projects.length === 1) setProjectId(projects[0].id);
  }, [projectId, projects, setProjectId]);

  return { projectId, setProjectId, projects, runs, loading: runs === null && !error, error };
}

export function discoverProjects(runs: RunSummary[]): DiscoveredProject[] {
  const grouped = new Map<string, RunSummary[]>();
  runs.forEach((run) => {
    if (run.project_id) grouped.set(run.project_id, [...(grouped.get(run.project_id) ?? []), run]);
  });
  return [...grouped.entries()].map(([id, projectRuns]) => {
    const workflows = [...new Set(projectRuns.map((run) => run.workflow_name?.trim()).filter(Boolean))] as string[];
    const context = workflows.length === 1 ? workflows[0] : null;
    return {
      id,
      label: context ? `${context} · ${id.slice(0, 8)}` : `Project ${id.slice(0, 8)}`,
      runCount: projectRuns.length,
    };
  }).sort((a, b) => a.label.localeCompare(b.label));
}

export function notifyApprovalCountChanged() {
  window.dispatchEvent(new Event(APPROVAL_CHANGED_EVENT));
}

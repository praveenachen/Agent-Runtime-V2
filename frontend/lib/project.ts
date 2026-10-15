"use client";

import { useSyncExternalStore } from "react";

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

export function notifyApprovalCountChanged() {
  window.dispatchEvent(new Event(APPROVAL_CHANGED_EVENT));
}

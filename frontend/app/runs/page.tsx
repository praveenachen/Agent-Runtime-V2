import { RunsList } from "@/components/runs-list";

export default function RunsPage() {
  return <main className="page-stack runs-page overview-page"><header className="page-heading"><div><h1>Runs</h1><p className="muted">Inspect and filter agent executions across your project.</p></div></header><RunsList /></main>;
}

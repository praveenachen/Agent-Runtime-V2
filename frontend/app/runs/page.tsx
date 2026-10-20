import { RunsList } from "@/components/runs-list";

export default function RunsPage() {
  return <main className="page-stack runs-page"><header className="page-heading"><div><p className="eyebrow">Execution history</p><h1>Runs</h1><p className="muted">Inspect and filter logical agent executions across your project.</p></div></header><RunsList /></main>;
}

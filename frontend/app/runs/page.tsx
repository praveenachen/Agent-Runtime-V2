import { RunsList } from "@/components/runs-list";

export default function RunsPage() {
  return <main className="page-stack"><header className="page-heading"><div><p className="eyebrow">Execution history</p><h1>Runs</h1><p className="muted">Inspect behavior from trace boundary to individual event.</p></div></header><RunsList /></main>;
}

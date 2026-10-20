import { OverviewDashboard } from "@/components/overview-dashboard";

export default function OverviewPage() {
  return (
    <main className="page-stack">
      <header className="page-heading">
        <div><p className="eyebrow">Control plane</p><h1>Overview</h1><p className="muted">Monitor, debug, and control your AI agent workflows.</p></div>
        <span className="live-indicator"><i /> Live telemetry</span>
      </header>
      <OverviewDashboard />
    </main>
  );
}

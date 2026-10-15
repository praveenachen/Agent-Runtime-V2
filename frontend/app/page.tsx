import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { MetricCard } from "@/components/ui/metric-card";

export default function OverviewPage() {
  return (
    <main className="page-stack">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Control plane</p>
          <h1>Overview</h1>
          <p className="muted">A calm, run-centric view of agent behavior.</p>
        </div>
        <Badge tone="healthy">Foundation ready</Badge>
      </header>

      <section className="metric-grid" aria-label="Runtime metrics">
        <MetricCard label="Active runs" value="—" hint="Telemetry arrives in Milestone 2" />
        <MetricCard label="Success rate" value="—" hint="Derived from completed runs" />
        <MetricCard label="Average latency" value="—" hint="Gold metrics arrive in Milestone 3" />
        <MetricCard label="Pending approvals" value="0" hint="Policy controls are deferred" />
      </section>

      <section className="content-grid">
        <Card title="Runtime activity" eyebrow="Runs">
          <div className="empty-state">
            <span className="pulse-dot" />
            <strong>Waiting for telemetry</strong>
            <p>Connect an OpenTelemetry-instrumented agent through the local Collector.</p>
          </div>
        </Card>
        <Card title="Architecture status" eyebrow="System">
          <ul className="status-list">
            <li><Badge tone="healthy">Ready</Badge><span>API foundation</span></li>
            <li><Badge tone="healthy">Ready</Badge><span>PostgreSQL migrations</span></li>
            <li><Badge tone="pending">Stub</Badge><span>OTel ingestion boundary</span></li>
            <li><Badge tone="pending">Deferred</Badge><span>Databricks pipeline</span></li>
          </ul>
        </Card>
      </section>
    </main>
  );
}


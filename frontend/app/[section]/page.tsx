import { notFound } from "next/navigation";

import { Card } from "@/components/ui/card";

const sections: Record<string, { title: string; description: string }> = {
  runs: { title: "Runs", description: "Execution history and graph inspection arrive in Milestone 3." },
  policies: { title: "Policies", description: "Deterministic runtime guardrails arrive in Milestone 6." },
  approvals: { title: "Approvals", description: "Human review workflows arrive in Milestone 6." },
  compare: { title: "Compare", description: "Runtime Diff and debugging replay arrive in Milestone 5." },
  settings: { title: "Settings", description: "Project and integration settings will grow with each milestone." },
};

export default async function SectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  const content = sections[section];
  if (!content) notFound();

  return (
    <main className="page-stack">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Workspace</p>
          <h1>{content.title}</h1>
        </div>
      </header>
      <Card title="Foundation placeholder" eyebrow="Coming next">
        <div className="empty-state compact">
          <strong>{content.description}</strong>
          <p>The navigation and route boundary are ready without simulating product data.</p>
        </div>
      </Card>
    </main>
  );
}


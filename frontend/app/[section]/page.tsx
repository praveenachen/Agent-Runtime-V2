import { notFound } from "next/navigation";

import { Card } from "@/components/ui/card";

const sections: Record<string, { title: string; description: string }> = {
  settings: { title: "Settings", description: "Project and integration settings are not configured in this local workspace." },
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
      <Card title="Workspace configuration" eyebrow="Settings">
        <div className="empty-state compact">
          <span className="state-icon">⌁</span>
          <strong>{content.description}</strong>
          <p>Runtime configuration is environment-managed. This screen intentionally exposes no controls until they are backed by an implemented product contract.</p>
        </div>
      </Card>
    </main>
  );
}


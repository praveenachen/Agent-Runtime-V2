import { RunDetail } from "@/components/run-detail";

export default async function RunDetailPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return <main className="page-stack run-detail-page"><RunDetail runId={runId} /></main>;
}

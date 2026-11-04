import { Suspense } from "react";
import { JobStatusView } from "@/components/job-status";

export default function JobPage({ params }: PageProps<"/jobs/[id]">) {
  return (
    <main>
      <h1>A processar a gravação</h1>
      <Suspense fallback={<p>A carregar…</p>}>
        <JobContent params={params} />
      </Suspense>
    </main>
  );
}

async function JobContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <JobStatusView jobId={id} />;
}

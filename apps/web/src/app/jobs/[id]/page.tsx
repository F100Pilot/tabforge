import { Suspense } from "react";
import { JobStatusView } from "@/components/job-status";

export default function JobPage({ params }: PageProps<"/jobs/[id]">) {
  return (
    <div className="page narrow">
      <Suspense fallback={<p className="muted">A carregar…</p>}>
        <JobContent params={params} />
      </Suspense>
    </div>
  );
}

async function JobContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <JobStatusView jobId={id} />;
}

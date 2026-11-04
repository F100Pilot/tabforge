import { Suspense } from "react";
import { TabEditor } from "@/components/tab-editor";

export default function EditTabPage({ params }: PageProps<"/tabs/[id]/edit">) {
  return (
    <div className="page editor-page">
      <Suspense fallback={<p className="muted">A carregar…</p>}>
        <EditContent params={params} />
      </Suspense>
    </div>
  );
}

async function EditContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TabEditor tabId={id} />;
}

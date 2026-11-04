import { Suspense } from "react";
import { TabViewer } from "@/components/tab-viewer";

export default function TabPage({ params }: PageProps<"/tabs/[id]">) {
  return (
    <div className="page wide">
      <Suspense fallback={<p className="muted">A carregar…</p>}>
        <TabContent params={params} />
      </Suspense>
    </div>
  );
}

async function TabContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TabViewer tabId={id} />;
}

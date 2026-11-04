import { Suspense } from "react";
import { TabViewer } from "@/components/tab-viewer";

export default function TabPage({ params }: PageProps<"/tabs/[id]">) {
  return (
    <main className="wide">
      <Suspense fallback={<p>A carregar…</p>}>
        <TabContent params={params} />
      </Suspense>
    </main>
  );
}

async function TabContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <TabViewer tabId={id} />;
}

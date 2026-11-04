import { Suspense } from "react";
import { HomeNotice } from "@/components/home-notice";
import { RecentJobs } from "@/components/recent-jobs";
import { UploadForm } from "@/components/upload-form";

export default function HomePage() {
  return (
    <div className="page">
      <Suspense fallback={null}>
        <HomeNotice />
      </Suspense>
      <h1>Nova tablatura</h1>
      <p className="subtitle">Carregue uma gravação. A IA escreve o rascunho; você afina no editor.</p>
      <div className="home-grid">
        <UploadForm />
        <RecentJobs />
      </div>
    </div>
  );
}

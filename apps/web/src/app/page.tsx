import { UploadForm } from "@/components/upload-form";

export default function HomePage() {
  return (
    <main>
      <h1>TabForge</h1>
      <p>Carregue uma gravação de guitarra e receba uma tablatura interativa.</p>
      <UploadForm />
    </main>
  );
}

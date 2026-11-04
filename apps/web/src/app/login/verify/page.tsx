import { VerifyLogin } from "@/components/verify-login";

export const metadata = { title: "Entrar · TabForge" };

export default function VerifyPage() {
  return (
    <div className="page narrow">
      <h1>Entrar</h1>
      <VerifyLogin />
    </div>
  );
}

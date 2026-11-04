import { LoginForm } from "@/components/login-form";

export const metadata = { title: "Iniciar sessão · TabForge" };

export default function LoginPage() {
  return (
    <div className="page narrow">
      <h1>Iniciar sessão</h1>
      <p className="subtitle">Introduza o seu email e enviamos-lhe um link para entrar.</p>
      <LoginForm />
    </div>
  );
}

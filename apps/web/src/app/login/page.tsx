import { LoginForm } from "@/components/login-form";
import { DESKTOP_RESTART_MESSAGE, IS_DESKTOP } from "@/lib/desktop";

export const metadata = { title: "Iniciar sessão · TabForge" };

export default function LoginPage() {
  if (IS_DESKTOP) {
    return (
      <div className="page narrow">
        <h1>Sessão local</h1>
        <p className="subtitle">{DESKTOP_RESTART_MESSAGE}</p>
      </div>
    );
  }
  return (
    <div className="page narrow">
      <h1>Iniciar sessão</h1>
      <p className="subtitle">Introduza o seu email e enviamos-lhe um link para entrar.</p>
      <LoginForm />
    </div>
  );
}

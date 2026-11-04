import Link from "next/link";
import { DESKTOP_RESTART_MESSAGE, IS_DESKTOP } from "@/lib/desktop";

/** Shown instead of a raw error when a protected API call answers 401. */
export function SignInPrompt() {
  if (IS_DESKTOP) {
    return (
      <div className="card empty" role="alert">
        <p>{DESKTOP_RESTART_MESSAGE}</p>
      </div>
    );
  }
  return (
    <div className="card empty" role="alert">
      <p>Inicie sessão para continuar.</p>
      <Link href="/login" className="btn btn-primary">
        Iniciar sessão
      </Link>
    </div>
  );
}

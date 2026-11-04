import Link from "next/link";

/** Shown instead of a raw error when a protected API call answers 401. */
export function SignInPrompt() {
  return (
    <div className="card empty" role="alert">
      <p>Inicie sessão para continuar.</p>
      <Link href="/login" className="btn btn-primary">
        Iniciar sessão
      </Link>
    </div>
  );
}

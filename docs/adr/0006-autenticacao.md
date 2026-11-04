# ADR-0006 — Autenticação: link mágico por email e sessões opacas no servidor

- **Estado:** Aceite
- **Data:** 2026-11-04
- **Fecha:** alternativa 3 do ADR-0001 (Supabase Auth), que ficava "reversível até ao início da US-07". Não se adota: a auth é própria, na API.

## Contexto

- A US-07 pede registo/login por email + Google e eliminação de conta com remoção de áudio, tabs e dados pessoais (RGPD art. 17).
- O threat model (T4, `docs/architecture.md`) exige cookies `HttpOnly`/`Secure`/`SameSite=Lax` e token CSRF.
- No M1 a API tinha só um stub (`dev_auth`); as rotas dependem apenas de `get_current_user`, por isso a troca não toca nas rotas.
- Restrições: sem dependências novas sem necessidade (`pip-audit --strict` no CI), API dona do schema (Alembic), web e API em origens diferentes em dev (`localhost:3000` → `localhost:8000`, mesmo site).

## Opções consideradas

| Opção | A favor | Contra |
|---|---|---|
| **Link mágico por email + sessão opaca em Postgres + token CSRF sincronizador** | Sem passwords para guardar ou recuperar; revogação imediata (apagar a linha); só stdlib (`secrets`, `hashlib`, `hmac`, `smtplib`) | Login depende da entrega de email; uma ida ao Postgres por pedido |
| Email + password | Não depende do email em cada login | Hashing (dependência nova: argon2/bcrypt), política de passwords, fluxo de recuperação (que é um link mágico na mesma) |
| JWT (stateless) | Sem leitura de BD por pedido | Revogação (logout, eliminação de conta) exige lista negra, ou seja, estado; mais fácil de errar (algoritmo, rotação de chaves); não há escala que o justifique |
| Supabase Auth (ADR-0001, opção 3) | Menos código de auth | Fornecedor externo com dados pessoais (DPA); segundo modelo de utilizadores fora do nosso Postgres; acoplamento |
| Auth.js (no Next.js) | Fornecedores OAuth prontos | Auth passa a viver no web, em TypeScript; a API (que é quem autoriza) teria de confiar num token emitido por outro serviço |

## Decisão

- **Login por link mágico.** `POST /v1/auth/magic-link {email}` responde sempre 202 a um email válido (sem enumeração de contas). Gera `secrets.token_urlsafe(32)`, guarda só o SHA-256 em `login_tokens` (TTL `login_token_ttl_s`, 15 min por defeito) e envia o link `{web_base_url}/login/verify#token=…`. O token vai no **fragmento**: o browser não o envia ao servidor, por isso não aparece em logs de acesso nem em `Referer`.
- **Consumo atómico e único.** `POST /v1/auth/verify {token}` faz `UPDATE … SET used_at = now() WHERE token_hash = … AND used_at IS NULL AND expires_at > now() RETURNING email`. Inválido, expirado ou já usado → 400 `invalid_token`. Cria o utilizador se não existir (email em minúsculas; índice único em `lower(email)`).
- **Sessão opaca no servidor.** Tabela `sessions` (`user_id` com `ON DELETE CASCADE`, SHA-256 do valor do cookie, `csrf_token`, `expires_at`; `session_ttl_days`, 30 por defeito, sem renovação). Cookie `tabforge_session`: `HttpOnly; SameSite=Lax; Path=/; Max-Age=…; Secure` (`Secure` só se desliga em dev por http). Um novo login substitui a sessão anterior do mesmo browser (sem fixação de sessão).
- **CSRF: token sincronizador.** `verify` e `GET /v1/auth/session` devolvem o `csrf_token` da sessão; pedidos `POST/PUT/PATCH/DELETE` autenticados por cookie têm de o enviar em `X-CSRF-Token` (comparação em tempo constante), senão 403 `csrf_failed`. `SameSite=Lax` é a primeira barreira; o token cobre o resto (subdomínios do mesmo site, browsers antigos).
- **CORS** com credenciais só para as origens configuradas (nunca `*`, recusado no arranque); cabeçalhos `Content-Type` e `X-CSRF-Token`.
- **Email por SMTP genérico** (`smtplib` da stdlib, timeout, STARTTLS e login opcionais), atrás de uma porta `Mailer`. Dev: Mailpit no compose. Sem `smtp_host`: em `env=dev` o link vai para o log; noutros ambientes a API não arranca (fail closed).
- **Limites** (T3): 5 pedidos de link por email e 20 por IP em 15 min → 429 `rate_limited` com `Retry-After` (em memória, como o limitador de escritas).
- **`dev_auth`** mantém-se só como fallback em `env=dev` quando não há cookie (sem CSRF, porque não há sessão).
- **Eliminação de conta** (`DELETE /v1/me`): apaga primeiro os objetos de áudio no storage; se o storage falhar → 503 `storage_unavailable` e nada é apagado na BD (o utilizador repete). Depois apaga os `login_tokens` do email e a linha do utilizador, que em cascata leva áudio, jobs, tabs, revisões e sessões. O worker trata um job cujo dono desapareceu como no-op.
- **Google OAuth fica para depois** (backlog). Entra como outra forma de chegar ao mesmo `verify` interno: cria/encontra o utilizador pelo email verificado e abre a mesma sessão.

## Consequências

- (+) Zero dependências novas; segredos nunca guardados em claro (só hashes).
- (+) Logout e eliminação de conta revogam imediatamente.
- (+) Sem passwords: nada para vazar, sem fluxo de recuperação.
- (−) Cada pedido autenticado lê a tabela `sessions` (índice único no hash; aceitável ao volume do MVP).
- (−) O login depende da entregabilidade do email (SPF/DKIM do domínio de envio em produção). Falha no envio → 503 `mail_unavailable`.
- (−) Limites em memória por instância: com várias réplicas o limite efetivo multiplica-se. Atrás de um proxy, o IP do cliente tem de vir do proxy (configurar `--forwarded-allow-ips` no uvicorn).
- (−) O web tem de ler o `csrf_token` (`GET /v1/auth/session`) e enviá-lo em todos os pedidos que alteram estado.

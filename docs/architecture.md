# Arquitetura — TabForge

Estado: **Proposta** (aguarda aprovação — gate da Fase 2).

## C4 — Nível 1 (Contexto)

```mermaid
flowchart LR
  U[Utilizador<br/>guitarrista/músico] -->|HTTPS| S[TabForge]
  S -->|OAuth| G[Google Identity]
  S -->|email transacional| E[Fornecedor de email]
```

## C4 — Nível 2 (Containers)

```mermaid
flowchart LR
  U[Browser] --> W[web<br/>Next.js + alphaTab]
  W -->|REST/JSON| A[api<br/>FastAPI · Python 3.13]
  A --> DB[(PostgreSQL<br/>dados + fila de jobs)]
  A -->|URLs pré-assinados| S3[(Object storage<br/>S3 / versitygw em dev)]
  K[worker<br/>Python 3.13 · Demucs + Basic Pitch ONNX] -->|SKIP LOCKED| DB
  K --> S3
  U -->|upload direto via URL pré-assinado| S3
```

| Container | Responsabilidade | Tecnologia |
|---|---|---|
| `apps/web` | UI, render/playback/edição de tab | Next.js 16, TypeScript strict, alphaTab 1.9 (MPL-2.0) |
| `services/api` | Auth, CRUD, criação de jobs, URLs pré-assinados, rate limiting | FastAPI, SQLAlchemy 2, Alembic |
| `services/worker` | Pipeline de transcrição | Python 3.13, Demucs 4.1 (MIT), Basic Pitch 0.4 (backend ONNX, sem TensorFlow) |
| PostgreSQL | Dados + fila (`jobs` com `FOR UPDATE SKIP LOCKED`) | Postgres 17 |
| Object storage | Áudio, stems, MIDI intermédio | S3 em produção, versitygw em dev (ADR-0004) |

Sem Redis/broker no MVP: a fila em Postgres chega para o volume previsto e remove um serviço (ADR-0001).

## Pipeline de transcrição (worker)

```mermaid
flowchart LR
  A[áudio] --> B[normalizar<br/>ffmpeg → 44.1k mono/estéreo]
  B --> C[separar<br/>Demucs htdemucs_6s → stem guitarra]
  C --> D[transcrever<br/>Basic Pitch → notas]
  B --> E[tempo/beats<br/>librosa]
  D --> F[quantizar ritmo]
  E --> F
  F --> G[atribuir corda/traste<br/>DP/Viterbi, custo ergonómico]
  G --> H[score JSON → alphaTex / GP]
```

- Etapas `B–E` são modelos de terceiros atrás de interfaces (`Separator`, `Transcriber`, `BeatTracker`) → substituíveis.
- Etapas `F–G` são **domínio próprio**, deterministas, com TDD (onde está o diferencial).
- Upload de stem já isolada (opção do utilizador) salta a etapa `C`.

## Modelo de dados (inicial)

```mermaid
erDiagram
  USER ||--o{ AUDIO_ASSET : uploads
  USER ||--o{ TAB : owns
  AUDIO_ASSET ||--o{ JOB : processed_by
  JOB ||--o| TAB : produces
  TAB ||--o{ TAB_REVISION : has
  USER { uuid id; text email; timestamptz created_at; timestamptz deleted_at }
  AUDIO_ASSET { uuid id; uuid user_id; text status; text source_kind; text content_type; bigint size_bytes; text storage_key; text sha256; int duration_ms; timestamptz expires_at }
  JOB { uuid id; uuid audio_id; text status; text stage; int attempts; text error_code; timestamptz locked_at; uuid tab_id }
  TAB { uuid id; uuid owner_id; text title; text tuning; text visibility; uuid current_revision_id }
  TAB_REVISION { uuid id; uuid tab_id; jsonb score; text source; timestamptz created_at }
```

- `AUDIO_ASSET.status`: `pending_upload | uploaded | rejected`; `source_kind`: `mix | guitar_stem` (escolha do utilizador no upload).
- `JOB.status`: `queued | running | done | failed`; `stage`: `separating | transcribing | arranging`. `guitar_stem` salta `separating` (ADR-0002, decisão M0).
- Fila: o worker reclama o job `queued` mais antigo (ou `running` com lease expirado) com `FOR UPDATE SKIP LOCKED`; cada etapa renova `locked_at`. Acima de 3 tentativas o job falha com `max_attempts_exceeded`; erro numa etapa → `failed` com `<etapa>_failed`.
- Schema: migrações Alembic em `services/api/migrations` (a API é dona do schema; o worker usa SQL via psycopg).
- `TAB.visibility`: `private` (default) `| unlisted | public` (public desativado até ADR-0003 ser fechado).
- `TAB_REVISION` imutável; `source`: `ai | user`.

## Contrato de API (rascunho)

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/v1/uploads` | `{content_type, size_bytes, source_kind}` → URL pré-assinado (PUT, assina `Content-Type` e `Content-Length`, ≤ 5 min) + `audio_id`; 413/415 |
| `POST` | `/v1/uploads/{id}/complete` | Confirma tamanho e magic bytes (se não coincidirem: apaga, 415); cria job `queued` |
| `GET` | `/v1/jobs/{id}` | Estado + etapa |
| `GET` | `/v1/tabs/{id}` | Tab + revisão atual (score) + alphaTex gerado no servidor |
| `POST` | `/v1/tabs/{id}/revisions` | Nova revisão (edição) |
| `GET` | `/v1/tabs/{id}/export?format=gp\|midi` | Export |
| `GET` | `/health`, `/ready` | Liveness / readiness |

OpenAPI gerado automaticamente pelo FastAPI (`/openapi.json`) é a fonte de verdade. Implementado no M1: uploads, jobs, `GET /v1/tabs/{id}`, `/health`, `/ready`.

### Validação de uploads (US-01)

- Tipo e tamanho declarados validados ao criar o upload (415/413); o URL pré-assinado assina ambos, por isso o storage rejeita outro conteúdo (403).
- Ao completar: tamanho real (HEAD) e magic bytes (GET com `Range`, 12 bytes). A API nunca descodifica áudio (T1).
- **Duração (≤ 10 min) é verificada no worker** (etapa de normalização, M2, ffprobe no container isolado), não na API: obrigaria a API a descodificar input não confiável. Consequência: um ficheiro longo devolve `failed` com `audio_too_long` no job, em vez de 413 no upload. Desvio ao critério de US-01, registado aqui.

### Autenticação no M1

- Stub: com `dev_auth` (só aceite com `env=dev`) todos os pedidos agem como um utilizador de dev; sem ele, `/v1` responde 401 (fail closed). As rotas dependem só de `get_current_user`, que a US-07 (M2) substitui.

## Erros, logging, configuração

- Erros: RFC 9457 (`application/problem+json`) com `code` estável.
- Logging: JSON estruturado, `request_id`/`job_id` correlacionados; sem emails nem nomes de ficheiro do utilizador.
- Config: env vars (12-factor); `.env.example` versionado.

## Threat model (STRIDE — top ameaças)

| # | Ameaça | Categoria | Mitigação |
|---|---|---|---|
| T1 | Ficheiro malicioso disfarçado de áudio (exploit em decoder ffmpeg) | Tampering / EoP | Validação por magic bytes; ffmpeg em container sem rede, utilizador não-root, limites CPU/mem/tempo; ffmpeg atualizado |
| T2 | Acesso a tabs/áudio de outro utilizador (IDOR) | Info disclosure | Autorização por `owner_id` em todas as queries; UUIDs; testes de autorização por rota |
| T3 | Abuso de GPU (DoS por custo) | DoS | Quotas por utilizador/dia, duração máx., rate limiting, dedupe por SHA-256 |
| T4 | Roubo de sessão | Spoofing | Cookies `HttpOnly`/`Secure`/`SameSite=Lax`, CSRF token, CSP estrita |
| T5 | XSS via título/metadados da tab ou alphaTex | Tampering | Escape no output; alphaTex gerado no servidor a partir de JSON validado (schema), nunca texto livre do utilizador |
| T6 | Fuga de URLs pré-assinados | Info disclosure | Expiração ≤ 5 min; bucket privado; sem listagem |
| T7 | Conteúdo protegido publicado | Repúdio / legal | Privado por defeito; declaração de titularidade; takedown e audit log (ADR-0003) |

## Decisões (ADRs)

- [ADR-0001](adr/0001-monorepo-e-stack.md) — Monorepo e stack
- [ADR-0002](adr/0002-pipeline-transcricao.md) — Pipeline de transcrição e isolamento do worker
- [ADR-0003](adr/0003-politica-conteudo-direitos-autor.md) — Política de conteúdo e direitos de autor
- [ADR-0004](adr/0004-s3-de-desenvolvimento.md) — Object storage de desenvolvimento: versitygw em vez de MinIO
- [ADR-0005](adr/0005-pacote-partilhado-score.md) — Pacote partilhado do score e Score v2

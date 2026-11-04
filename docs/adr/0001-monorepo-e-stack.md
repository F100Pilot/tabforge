# ADR-0001 — Monorepo e stack

- **Estado:** Proposto
- **Data:** 2026-11-04

## Contexto

Três componentes com ciclos de vida diferentes (UI, API, worker ML) e uma equipa pequena. O worker ML tem dependências pesadas (PyTorch, ONNX Runtime) que não devem entrar na imagem da API (ADR-0002).

## Opções consideradas

1. **Monorepo: Next.js + FastAPI + worker Python + Postgres (fila) + S3** — escolhida.
2. Next.js full-stack (route handlers como API) + worker Python — menos um serviço, mas lógica de domínio dividida entre TS e Python e dois modelos de dados.
3. BaaS (Supabase: Auth + Postgres + Storage) + worker — menos código de auth/storage; acoplamento ao fornecedor e menos controlo sobre o pipeline de upload.
4. Broker dedicado (Redis/RabbitMQ + Celery) — desnecessário ao volume do MVP.

## Decisão

- Monorepo com `apps/web`, `services/api`, `services/worker`.
- Frontend: Next.js 16 (App Router), TypeScript strict, alphaTab 1.9 para render/playback.
- API: FastAPI (Python 3.13), SQLAlchemy 2 + Alembic, `uv` para dependências com lockfile.
- Fila: tabela `jobs` em Postgres com `SELECT … FOR UPDATE SKIP LOCKED`.
- Storage: S3-compatível (MinIO em dev).

## Consequências

- (+) Python 3.13 partilhado entre API e worker (modelos Pydantic do score reutilizáveis via pacote comum, se necessário).
- (+) Um serviço a menos (sem broker).
- (−) Dois runtimes (Node + Python) no CI.
- (−) Fila em Postgres não escala para milhares de jobs/s — reavaliar acima de ~10 jobs/s sustentados.
- Opção 3 (Supabase) fica como alternativa válida se se quiser reduzir o trabalho de auth; reversível até ao início da US-07.

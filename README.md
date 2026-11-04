# TabForge

Tablaturas de guitarra interativas (render, playback, edição) geradas a partir de áudio com IA.

> Estado: **walking skeleton**. Arquitetura proposta, aguarda aprovação. Ver [`docs/`](docs/).

## Estrutura

```
apps/web/          Next.js 16 + TypeScript (UI; alphaTab a partir do M1)
services/api/      FastAPI · Python 3.13
services/worker/   Pipeline de transcrição · Python 3.13 (Demucs + Basic Pitch ONNX)
docs/              PRD, arquitetura, ADRs, backlog
```

## Requisitos

- Node 22 + pnpm 10
- [uv](https://docs.astral.sh/uv/) (gere o Python 3.13 automaticamente)
- Docker (Postgres + MinIO locais)

## Setup

```bash
cp .env.example .env                       # editar passwords
docker compose up -d postgres minio
cd services/api && uv sync && uv run uvicorn tabforge_api.main:create_app --factory --reload
cd apps/web && pnpm install && pnpm dev    # http://localhost:3000
```

Worker com stack ML (pesado, ~GBs): `cd services/worker && uv sync --extra ml`.

## Qualidade

| Componente | Comandos |
|---|---|
| web | `pnpm lint && pnpm typecheck && pnpm test && pnpm build` |
| api / worker | `uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest` |

Pre-commit: `uvx pre-commit install` (correr `uvx pre-commit autoupdate` na primeira vez).

## Convenções

- Trunk-based, feature branches curtas, [Conventional Commits](https://www.conventionalcommits.org/).
- Segredos só em `.env` (ignorado). Nunca commitar áudio com direitos de autor.
- Decisões de arquitetura em `docs/adr/`.

## Licença

Por definir antes do primeiro release público. Dependências de terceiros em [`docs/THIRD_PARTY.md`](docs/THIRD_PARTY.md).

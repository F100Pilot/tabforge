# TabForge

Tablaturas de guitarra interativas (render, playback, edição) geradas a partir de áudio com IA.

> Estado: **M1 — walking skeleton** (upload → fila → pipeline stub → tab renderizada). M0 em [`docs/eval/M0-baseline.md`](docs/eval/M0-baseline.md). Ver [`docs/`](docs/).

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
- Docker (Postgres + S3 local via versitygw, ADR-0004)

## Setup

```bash
cp .env.example .env                       # editar passwords
docker compose up -d --build               # postgres, s3, migrate (Alembic + bucket), api, worker
cd apps/web && pnpm install && pnpm dev    # http://localhost:3000
```

Em M1 a autenticação é um stub: com `TABFORGE_DEV_AUTH=true` (só aceite com `TABFORGE_ENV=dev`) todos os pedidos usam um utilizador de dev. Sem isso, as rotas `/v1` respondem 401.

Worker com stack ML (pesado, ~GBs): `cd services/worker && uv sync --extra ml`.

## Windows (uso pessoal, ADR-0008)

Requisito: [Git para Windows](https://git-scm.com/download/win). O resto (uv, Python, PostgreSQL, Node, ffmpeg, pesos do Demucs) é instalado pelo script na primeira vez.

```bat
git clone https://github.com/F100Pilot/tabforge.git
cd tabforge
start.bat
```

- Cada `start.bat` faz `git pull`, atualiza as dependências, recompila a interface só se mudou e abre o TabForge numa janela.
- `start.bat --smoke` corre um autoteste sem janela (uma transcrição real).
- Dados (base de dados, áudio, registos): `%LOCALAPPDATA%\TabForge`. Não saem do PC.
- O instalador `TabForge-Setup.exe` é gerado pelo workflow `Desktop (Windows)` como artefacto, só a pedido ("Run workflow"; ADR-0012). Em cada push o CI testa o `start.bat`.

## Qualidade

| Componente | Comandos |
|---|---|
| web | `pnpm lint && pnpm typecheck && pnpm test && pnpm build` |
| api / worker | `uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest` |
| api / worker (integração) | definir `TABFORGE_TEST_DATABASE_URL` (Postgres) e `TABFORGE_TEST_S3_ENDPOINT` (S3); sem elas os testes `db`/`s3` são saltados |
| worker (ML) | `uv sync --extra ml --extra eval && uv run pytest -m ml` |

Pre-commit: `uvx pre-commit install` (correr `uvx pre-commit autoupdate` na primeira vez).

## Convenções

- Trunk-based, feature branches curtas, [Conventional Commits](https://www.conventionalcommits.org/).
- Segredos só em `.env` (ignorado). Nunca commitar áudio com direitos de autor.
- Decisões de arquitetura em `docs/adr/`.

## Licença

Por definir antes do primeiro release público. Dependências de terceiros em [`docs/THIRD_PARTY.md`](docs/THIRD_PARTY.md).

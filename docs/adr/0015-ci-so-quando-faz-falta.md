# ADR-0015 — Workflows do GitHub Actions só quando o que testam muda

- **Estado:** Aceite
- **Data:** 2026-11-11
- **Substitui:** a frase "em cada push para `main` (e PRs)" do ADR-0012 (o resto do ADR-0012 mantém-se)

## Contexto

- Cada push para `main` corria quatro jobs pesados: CI (lint, testes, build, e2e), a imagem Docker do worker (torch e modelos), CodeQL e o smoke test do `start.bat` em Windows. Os minutos de Windows contam a dobrar.
- O utilizador testa com `git pull` no PC e pediu para gastar menos no Actions.
- O TabForge corre no PC (ADR-0008). As imagens Docker são da versão online, que ainda não está no ar.

## Decisão

- **CI** (`ci.yml`): em cada push e PR, exceto quando só mudam `*.md` ou `docs/`.
- **Desktop (Windows)** (`desktop.yml`): o smoke test do `start.bat` só corre quando muda o que o launcher instala ou corre: `apps/desktop/`, `start.bat`, os `pyproject.toml`/`uv.lock` dos serviços e pacotes, ou o próprio workflow. O instalador continua só a pedido (ADR-0012); "Run workflow" corre também o smoke test.
- **Docker** (`docker.yml`, antes um job do CI): só quando mudam os Dockerfiles, as dependências Python, `.dockerignore`, `docker-compose.yml` ou `.env.example`; também à segunda-feira e a pedido.
- **CodeQL** (`codeql.yml`): à segunda-feira, a pedido e nos PRs; não em cada push.

## Consequências

- (+) Um push que só mexe na interface ou na API corre só o CI, em Linux.
- (−) Uma regressão que só aparece em Windows numa alteração da interface, da API ou do worker sem mudança de dependências só se vê no PC do utilizador ou no próximo smoke test (o CI em Linux testa o mesmo código).
- (−) Um problema de segurança detetado pelo CodeQL aparece até uma semana mais tarde.
- (−) Uma alteração de código que parta a imagem Docker sem mudar dependências só se vê na execução de segunda-feira.

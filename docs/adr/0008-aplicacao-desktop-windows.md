# ADR-0008 — Aplicação desktop para Windows (uso pessoal, GPU NVIDIA)

- **Estado:** Aceite
- **Data:** 2026-11-04

## Contexto

- O TabForge vai ser usado, para já, por uma só pessoa, num PC Windows com GPU NVIDIA (RTX 4080 SUPER, arquitetura Ada, sm_89). Inicialmente registado como "sem GPU"; corrigido pelo utilizador. Pôr a versão web online exige alojamento, worker com GPU, SMTP, domínio, operação e RGPD do lado do servidor, sem utilizadores que o justifiquem.
- O utilizador escolheu um instalador `.exe` nativo, sem Docker. Uma versão online fica para mais tarde, se valer a pena.
- O ADR-0001 define a stack web (Next.js + FastAPI + worker + Postgres + S3). O ADR-0002 restringe o lock do worker a Linux.
- A API e o worker usam funcionalidades de Postgres (58 usos: `FOR UPDATE SKIP LOCKED`, `ON CONFLICT`, `FOR KEY SHARE`, SQL do psycopg no worker). Portar para SQLite duplicaria o acesso a dados.

## Opções consideradas

1. **Programa de arranque Python que embute os serviços existentes** — Postgres portátil, API e worker no mesmo processo, servidor Next.js com Node embutido, janela WebView2 — escolhida.
2. Docker Desktop + atalho — zero código novo, mas o utilizador recusou o Docker.
3. Reescrever para SQLite + armazenamento local num executável único — mais pequeno, mas dois caminhos de dados para manter quando passar para online.
4. Tauri (Rust) como invólucro — janela mais leve, mas acrescenta um toolchain Rust e continua a precisar dos mesmos serviços Python e Node.

## Decisão

- **Modo `env=desktop` nos serviços**, sem tocar no comportamento online:
  - **Utilizador local:** um único utilizador. O programa de arranque gera um token por arranque; `POST /v1/auth/desktop` troca-o pela sessão e token CSRF normais (ADR-0006), por isso o mesmo código de sessão e CSRF protege o modo desktop. Sem SMTP.
  - **Só local:** a API e a web escutam apenas em `127.0.0.1`; a API recusa `Host` diferente de `127.0.0.1`/`localhost` (proteção contra DNS rebinding).
  - **Sem quota nem expiração:** a quota diária de uploads (T3) e a retenção de 30 dias do áudio original não se aplicam: um só utilizador, no próprio PC. O worker continua a limpar uploads abandonados (> 1 dia).
  - **Armazenamento:** `LocalObjectStore` numa pasta, com rota de upload assinada (HMAC, validade ≤ 300 s, tamanho e tipo verificados) que substitui o URL pré-assinado do S3. O worker lê o ficheiro diretamente.
- **`apps/desktop`:** pacote Python com o programa de arranque e o seu próprio `pyproject.toml`/`uv.lock` para Windows (e Linux, para testes). Inclui a API, o worker e o pacote do score como dependências por caminho, e o `torch` 2.15.0+cu132 do índice do PyTorch em Windows (2,11 GB, bibliotecas CUDA incluídas; a mais antiga das duas builds CUDA dessa versão, para exigir o driver menos recente). Em Linux (só testes) fica o `torch` do PyPI. O Demucs usa a GPU quando `torch.cuda.is_available()` e cai para CPU sem driver utilizável. O stack ML fica num extra `bundle`, instalado só no build Windows; os testes em Linux correm sem ele. Repete os overrides do ADR-0002 (sem TensorFlow, `resampy>=0.4.3`, `torch>=2.6`) e passa pelo mesmo `pip-audit --strict`. O lock do worker continua restrito a Linux.
- **Postgres:** binários oficiais do PostgreSQL 17 para Windows, descarregados no CI com checksum fixado. Os dados ficam em `%LOCALAPPDATA%\TabForge`, com escuta só em `127.0.0.1`, porta livre e password gerada no primeiro arranque. As migrações Alembic correm em cada arranque.
- **Web:** Next.js com `output: "standalone"`, servido por um Node LTS embutido. Portas fixas locais: web `127.0.0.1:47800`, API `127.0.0.1:47801`; o `NEXT_PUBLIC_API_URL` é fixado no build.
- **Janela:** `pywebview` (BSD-3) sobre o Edge WebView2, que já vem no Windows 10/11; se falhar, abre o browser predefinido.
- **ffmpeg:** build LGPL para Windows, com checksum fixado.
- **Empacotamento:** PyInstaller (`--onedir`) + Inno Setup → `TabForge-Setup.exe`, artefacto do CI. Sem assinatura de código e sem atualizações automáticas (uso pessoal: o aviso do SmartScreen é aceite).
- **CI:** job `windows-latest` que constrói o instalador e faz um smoke test ao programa empacotado sem janela: arranca o Postgres, migra, carrega um WAV pela API, espera pela tab e desliga tudo.

## Consequências

- (+) Sem servidor, sem custos e sem login; o áudio nunca sai do PC.
- (+) A versão online continua igual. Passar para online mais tarde é pôr no ar a stack que já existe e é testada no CI.
- (+) Um só caminho de dados (Postgres) e o mesmo código de sessão e CSRF nos dois modos.
- (−) Instalação grande (PyTorch com CUDA ~2,1 GB, Demucs, Postgres, Node). Exige um driver NVIDIA recente para usar a GPU.
- (+) Separação de misturas com o Demucs na GPU; sem driver compatível corre em CPU, mais lenta. Guitarra isolada não usa o Demucs.
- (−) Só testável em Windows pelo CI (smoke test sem interação); a janela é verificada manualmente pelo utilizador.
- (−) Dois locks de Python a manter (Linux para os contentores, desktop para Windows).
- (−) Antivírus podem marcar executáveis PyInstaller não assinados.

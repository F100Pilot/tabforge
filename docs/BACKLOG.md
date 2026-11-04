# Backlog

## Definition of Ready
- Story com critérios Given/When/Then; dependências identificadas; tamanho ≤ 1 dia.

## Definition of Done
- Código + testes (unit; integração onde há I/O) · lint/type check verdes · review sem achados Critical/High · docs/ADR atualizados · CI verde.

## M0 — Spike de qualidade (antes de investir em UI)
- [ ] Montar set de avaliação: 20 clips de **gravações próprias** (isolada e em mistura com banda) com tab de referência. Serve para avaliar a mistura e a guitarra fora do treino do Basic Pitch (decisão M0). Correr com `eval/run_m0.py` adaptado
- [x] Script de avaliação: note F1 (mir_eval) — `services/worker/eval/`. Precisão corda/traste fica para o M2 (não há atribuição ainda)
- [x] Baseline Demucs 6s + Basic Pitch; registar resultados em `docs/eval/` — `docs/eval/M0-baseline.md` (guitarra isolada; mistura por medir)
- [x] Decisão go/no-go sobre a abordagem (ADR-0002): **go para guitarra isolada**; mistura avaliada com gravações próprias

## M1 — Walking skeleton
- [x] Monorepo, CI, docker-compose (Postgres, MinIO)
- [x] API: migrações iniciais (users, audio_assets, jobs, tabs, tab_revisions)
- [x] Upload pré-assinado + validação (US-01): tipo/tamanho (413/415) e magic bytes; duração passa para o worker no M2 (ver architecture.md)
- [x] Worker: loop de fila SKIP LOCKED com etapas stub; etapa de separação só para input em mistura (stem isolada salta o Demucs, ADR-0002)
- [x] Teste de integração: inferência Basic Pitch ONNX real num clip sintético (guarda os overrides do ADR-0002) — feito no M0
- [x] Web: página que renderiza o alphaTex da API com playback e velocidade 25–150% (US-03 parcial; falta loop de secção)
- [x] Fluxo ponta-a-ponta com pipeline stub, verificado no Chromium contra API, worker e S3 reais. Automatizar em CI fica no item E2E Playwright do M2

## M2 — MVP
- [x] Wireframes (upload, progresso, viewer, editor) aprovados antes de começar a UI do M2 (Fase 2 do SDLC) — decisões em `docs/ui/design.md`
- [x] Tema da pauta claro/escuro à escolha do utilizador (preferência guardada no browser). alphaTab 1.9 `display.resources`, paletas validadas no render dos wireframes:
  - escura: fundo `#14171C`, mainGlyph `#E6E8EB`, secondaryGlyph `#9AA1AC`, staffLine `#4A505B`, barSeparator `#8A919C`, barNumber `#F2B544`, scoreInfo `#C9CED6`
  - clara: fundo `#FAFAF7`, mainGlyph `#1B1D21`, secondaryGlyph `#6B7079`, staffLine `#A3A39B`, barSeparator `#4A4E55`, barNumber `#9A6A12`, scoreInfo `#1B1D21`
- [x] Domínio: quantização rítmica (TDD), a partir de onsets e beats, sem depender de offsets do Basic Pitch (M0: F1 com offset de 0,55)
- [x] Domínio: atribuição corda/traste Viterbi (TDD) — 65,7% exato em guitaristas de teste do GuitarSet (`docs/eval/M2-arranging.md`)
- [x] Integração Demucs/Basic Pitch/librosa no worker (US-02), com etapa `normalizing` (ffmpeg, limite de 10 min)
- [x] Auth por email (link mágico) e eliminação de conta (US-07, ADR-0006): sessão opaca em Postgres, cookie `HttpOnly`/`Secure`/`SameSite=Lax`, token CSRF, SMTP genérico (Mailpit em dev); `DELETE /v1/me` apaga áudio no storage e depois o utilizador em cascata; o worker apaga tokens e sessões expirados
- [ ] Login com Google (OAuth) (US-07) — adiado; reutiliza a mesma sessão (ADR-0006)
- [ ] Eliminação de conta: um upload pré-assinado emitido antes do `DELETE /v1/me` pode ainda chegar ao storage (≤ 5 min) sem linha na BD. Fechar com regra de lifecycle do bucket para `audio/` órfãos ou limpeza por prefixo `audio/{user_id}/`
- [ ] Rate limiting partilhado entre réplicas (Postgres/Redis) e IP real atrás de proxy (`--forwarded-allow-ips`) — hoje em memória por instância
- [x] Editor de tab com revisões (US-04): traste/corda com ligaduras, anular/refazer, Ctrl+S, conflito 409, histórico de revisões. Edição de ritmo fica para o M3
- [x] Quotas, rate limiting, retenção de áudio — 20 uploads/24 h, 30 escritas/min por utilizador (em memória, uma instância), worker apaga áudio expirado (30 dias) e uploads abandonados (>1 dia)
- [x] E2E Playwright no CI (job `e2e`, pipeline stub): login por link → upload → tab → editar e guardar → terminar sessão → eliminar conta

## M3 — Iterações
- [x] Export Guitar Pro (.gp) e MIDI no browser com o alphaTab, PDF por impressão na paleta clara (US-05, ADR-0007)
- [ ] Partilha pública (US-06) — bloqueado por ADR-0003

- [ ] Comparar e afinar (depois do PR #9): importar a tab certa (.gp 3–7 via alphaTab) de uma música já transcrita, alinhar com a versão da IA (introduções, repetições, tempo), mostrar métricas (notas encontradas, posições corretas)
- [ ] Afinar os pesos de corda/traste (Viterbi) por utilizador com as tabs certas importadas e com os pares revisão IA → revisão corrigida no editor; aplicar às tabs novas e medir antes/depois
- [ ] Afinar a quantização (tercinas, pausas, tempo) com pares áudio + tab certa alinhados
- [ ] (Reavaliar com dados suficientes) fine-tuning da deteção de notas — o treino do Basic Pitch usa TensorFlow (excluído, ADR-0002) e o modelo ONNX não é treinável diretamente

## Desktop (ADR-0008)
- [x] Fase 1 — modo `env=desktop` na API e no worker: `LocalObjectStore` e `PUT /v1/local-storage/{key}` assinado (HMAC, ≤ 300 s, tipo e tamanho verificados), `POST /v1/auth/desktop` com token de arranque (sessão e CSRF do ADR-0006), link mágico desativado (404), `Host` só loopback, worker com fonte local, retenção a apagar ficheiros locais, ffmpeg/ffprobe configuráveis e `run_forever` para correr o loop numa thread
- [ ] Programa de arranque `apps/desktop` (`pyproject.toml`/`uv.lock` próprios, `torch` CPU, overrides do ADR-0002, `pip-audit --strict`): gera os segredos por arranque, arranca API e worker no mesmo processo; a web troca o token em `POST /v1/auth/desktop`
- [ ] Postgres 17 embutido (binários oficiais com checksum fixado, dados em `%LOCALAPPDATA%\TabForge`, só `127.0.0.1`, porta livre, password gerada, migrações Alembic em cada arranque)
- [ ] Web com Next.js `output: "standalone"` servida por Node LTS embutido (`127.0.0.1:47800`, `NEXT_PUBLIC_API_URL` fixado no build)
- [ ] Janela `pywebview` sobre o WebView2, com recurso ao browser predefinido
- [ ] Empacotamento PyInstaller (`--onedir`) + Inno Setup → `TabForge-Setup.exe`, com ffmpeg LGPL embutido (checksum fixado)
- [ ] CI `windows-latest`: constrói o instalador e faz smoke test sem janela (Postgres, migrações, upload de um WAV, espera pela tab, encerra)

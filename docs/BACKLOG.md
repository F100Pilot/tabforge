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
- [ ] Wireframes (upload, progresso, viewer, editor) aprovados antes de começar a UI do M2 (Fase 2 do SDLC)
- [ ] Tema da pauta claro/escuro à escolha do utilizador (preferência guardada; por defeito segue o tema da interface). alphaTab 1.9 `display.resources`, paletas validadas no render dos wireframes:
  - escura: fundo `#14171C`, mainGlyph `#E6E8EB`, secondaryGlyph `#9AA1AC`, staffLine `#4A505B`, barSeparator `#8A919C`, barNumber `#F2B544`, scoreInfo `#C9CED6`
  - clara: fundo `#FAFAF7`, mainGlyph `#1B1D21`, secondaryGlyph `#6B7079`, staffLine `#A3A39B`, barSeparator `#4A4E55`, barNumber `#9A6A12`, scoreInfo `#1B1D21`
- [ ] Domínio: quantização rítmica (TDD), a partir de onsets e beats, sem depender de offsets do Basic Pitch (M0: F1 com offset de 0,55)
- [ ] Domínio: atribuição corda/traste Viterbi (TDD)
- [ ] Integração Demucs/Basic Pitch/librosa no worker (US-02)
- [ ] Auth email + Google, eliminação de conta (US-07)
- [ ] Editor de tab com revisões (US-04)
- [ ] Quotas, rate limiting, retenção de áudio
- [ ] E2E Playwright: upload → tab → editar

## M3 — Iterações
- [ ] Export GP/MIDI (US-05)
- [ ] Partilha pública (US-06) — bloqueado por ADR-0003

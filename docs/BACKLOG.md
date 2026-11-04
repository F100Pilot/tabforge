# Backlog

## Definition of Ready
- Story com critérios Given/When/Then; dependências identificadas; tamanho ≤ 1 dia.

## Definition of Done
- Código + testes (unit; integração onde há I/O) · lint/type check verdes · review sem achados Critical/High · docs/ADR atualizados · CI verde.

## M0 — Spike de qualidade (antes de investir em UI)
- [ ] Montar set de avaliação: 20 clips de guitarra (isolada e em mix) com tab de referência **de direitos livres ou próprios**
- [ ] Script de avaliação: note F1 (mir_eval), precisão corda/traste
- [ ] Baseline Demucs 6s + Basic Pitch; registar resultados em `docs/eval/`
- [ ] Decisão go/no-go sobre a abordagem (atualizar ADR-0002)

## M1 — Walking skeleton
- [x] Monorepo, CI, docker-compose (Postgres, MinIO)
- [ ] API: migrações iniciais (users, audio_assets, jobs, tabs, tab_revisions)
- [ ] Upload pré-assinado + validação (US-01)
- [ ] Worker: loop de fila SKIP LOCKED com etapas stub
- [ ] Teste de integração: inferência Basic Pitch ONNX real num clip sintético (guarda os overrides do ADR-0002)
- [ ] Web: página que renderiza um alphaTex fixo com playback (US-03 parcial)
- [ ] Fluxo ponta-a-ponta com pipeline stub

## M2 — MVP
- [ ] Domínio: quantização rítmica (TDD)
- [ ] Domínio: atribuição corda/traste Viterbi (TDD)
- [ ] Integração Demucs/Basic Pitch/librosa no worker (US-02)
- [ ] Auth email + Google, eliminação de conta (US-07)
- [ ] Editor de tab com revisões (US-04)
- [ ] Quotas, rate limiting, retenção de áudio
- [ ] E2E Playwright: upload → tab → editar

## M3 — Iterações
- [ ] Export GP/MIDI (US-05)
- [ ] Partilha pública (US-06) — bloqueado por ADR-0003

# ADR-0007 — Export Guitar Pro e MIDI no browser com o alphaTab

- **Estado:** Aceite
- **Data:** 2026-11-04

## Contexto

- A US-05 pede export para Guitar Pro (`.gp`) e MIDI, e PDF via impressão.
- `docs/architecture.md` previa um endpoint `GET /v1/tabs/{id}/export?format=gp|midi` na API.
- O browser já carrega o alphaTab 1.9.0 (MPL-2.0) para desenhar e tocar a tab, a partir do alphaTex gerado pelo servidor (`tabforge_score.to_alphatex`). O alphaTab inclui `exporter.Gp7Exporter` e `midi.MidiFileGenerator`/`MidiFile.toBinary()`.
- Do lado Python não há escritor de GP7 mantido; o `pyguitarpro` só escreve GP3–5 e é LGPL-3.0. MIDI exigiria outra dependência ou código próprio.

## Opções consideradas

1. **Export no browser com o alphaTab**, a partir do alphaTex da revisão atual — escolhida.
2. Endpoint na API com `pyguitarpro` (GP5) e `mido` (MIDI) — duas dependências novas, formato GP antigo, e um segundo conversor score → notas que pode divergir do que o utilizador vê e ouve.
3. Endpoint na API a correr o alphaTab em Node — um runtime novo no backend só para isto.

## Decisão

- `apps/web/src/lib/export.ts`: `ScoreLoader.loadAlphaTex` → `Gp7Exporter` (`.gp`, contentor zip GP7) ou `MidiFileGenerator` com `MidiFile` em formato multi-track (SMF tipo 1, `.mid`). O título da tab vai para os metadados GP e para o nome do ficheiro, sem caracteres proibidos em sistemas de ficheiros, até 80 caracteres e `tablatura` por omissão.
- PDF: impressão do browser. O viewer passa a pauta para a paleta clara antes de abrir o diálogo e repõe o tema escolhido no fim (`afterprint`). A folha de estilos de impressão esconde a navegação e o leitor.
- O endpoint `GET /v1/tabs/{id}/export` sai do plano da API.

## Consequências

- (+) Sem dependências novas; o ficheiro exportado sai do mesmo modelo que é desenhado e tocado.
- (+) Testes unitários fazem ida e volta GP7 → importação com as mesmas cordas, trastes, ligaduras, tempo e título; o E2E descarrega os dois formatos.
- (−) Não há export pela API para clientes de terceiros. Reavaliar se surgir uma API pública (correr o mesmo código do alphaTab em Node).
- (−) A fidelidade do export depende do alphaTab; atualizações do alphaTab têm de passar os testes de ida e volta.

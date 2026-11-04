# ADR-0009 — Comparação com a tab certa dentro do TabForge

- **Estado:** Aceite
- **Data:** 2026-11-04

## Contexto

- O utilizador quer comparar, dentro do programa, a tab gerada com a tab certa da mesma música, e usar essas comparações para afinar o algoritmo (BACKLOG M3).
- As tabs certas vêm normalmente em Guitar Pro (.gp3–.gp7). Do lado Python não há leitor de GP7 mantido (ADR-0007); o alphaTab, que o browser já carrega, lê GP3–7.
- As duas tabs raramente começam no mesmo sítio (introdução, contagem) e o andamento detetado pode ser o dobro ou metade do real.

## Opções consideradas

1. **O browser lê o ficheiro com o alphaTab e envia à API só as notas** (início em semínimas, pitch, corda, traste, compasso). A API guarda-as e calcula a comparação em Python — escolhida.
2. Enviar o ficheiro .gp à API — exige um leitor GP no Python (inexistente para GP7) ou Node no backend.
3. Comparar só no browser — a afinação do algoritmo (worker, Python) precisaria de repetir a lógica.

## Decisão

- `packages/score/compare.py` (puro, TDD): `score_events(Score)` e `compare(ai, referência)`.
  - Procura o deslocamento (até 64 compassos) e a escala de tempo (1, ½, 2) com mais notas alinhadas. Depois emparelha uma a uma notas com o mesmo pitch, com tolerância de uma semicolcheia.
  - Mede notas encontradas (recall), notas inventadas (precision), F1, posição correta (mesma corda e traste), erro médio de ataque e resultados por compasso da tab certa.
- API: uma referência por tab (`tab_references`, notas em JSONB, apagada com a tab), `PUT/GET/DELETE /v1/tabs/{id}/reference` e `GET /v1/tabs/{id}/comparison`. A comparação usa a revisão atual da tab.
- Web: botão "Comparar com a tab certa" na página da tab: escolher o ficheiro e a pista de guitarra, enviar as notas, mostrar as métricas e os compassos com mais diferenças.

## Consequências

- (+) Sem dependências novas; o mesmo código de comparação serve depois para afinar os pesos de corda/traste no worker.
- (+) A tab certa nunca sai do PC no modo desktop; só as notas são guardadas.
- (−) Repetições da tab certa não são expandidas: uma secção escrita uma vez com sinal de repetição é comparada uma vez.
- (−) Notas com o pitch errado (ex.: oitava) contam como não encontradas, mesmo que o ritmo esteja certo.

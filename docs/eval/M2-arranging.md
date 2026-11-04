# M2 — Quantização e atribuição corda/traste

- **Data:** 2026-11-04
- **Código:** `services/worker/src/tabforge_worker/arrange/` (`quantize`, `fretting`, `layout`)
- Números de execuções reais; nenhum valor estimado.

## Corda/traste (Viterbi) sobre os pitches de referência do GuitarSet

Entrada: as notas anotadas (pitch e onset; notas a menos de 30 ms juntam-se num acorde). Métrica: corda **e** traste iguais à anotação. Sem áudio, por isso isola a qualidade da atribuição.

| Método | Guitaristas | Notas | Acerto exato |
|---|---|---|---|
| Regra "traste mais baixo" (M0) | todos | 62 476 | 45,4% |
| Viterbi, pesos iniciais | 03–05 (teste) | — | 62,5% |
| **Viterbi, pesos finais** | **03–05 (teste)** | — | **65,7%** |
| Viterbi, pesos finais | todos (inclui treino) | 62 476 | 68,1% (comp 75,8%, solo 38,0%) |

Escolha dos pesos (`fretting.Weights`): grelha de 108 combinações avaliada nos guitarristas 00–02. Ficou a melhor no treino entre as que mantêm uma escala aberta de Mi a Ré na primeira posição (teste unitário). A combinação com melhor treino absoluto (71,6%) subia essa escala pela 6.ª corda até ao traste 10: foi rejeitada por contrariar a prática comum, apesar de melhor nos dados. Valores finais: span 1,0, altura 0,05, deslocação 0,5, deslocação a partir de cordas soltas 0,25.

Leitura:
- Acompanhamento (acordes) fica em 76%: as formas de acorde restringem bem as posições.
- Solos ficam em 38%: guitarristas de jazz/funk tocam linhas em posições altas e variadas; com só pitch e tempo, várias posições são igualmente plausíveis. É aqui que o editor ("mesma nota noutra posição", um clique) compensa.

## Robustez da cadeia quantização → Viterbi → layout

Notas e batidas anotadas dos 360 tracks → Score v2:
- 360/360 scores válidos (`tabforge_score.Score`), 5 276 compassos, 986 batidas em tercina, 35 notas marcadas com aviso.
- alphaTex de 5 tracks (um por estilo) lido pelo alphaTab 1.9 sem diagnósticos.

## Limitações conhecidas

- Compasso 4/4 fixo e sem deteção de tempo forte: o compasso 1 começa na batida antes da primeira nota.
- A qualidade do ritmo quantizado ainda não tem métrica própria (falta referência rítmica em notação); fica para o set de gravações próprias.
- GuitarSet é guitarra acústica em afinação standard.

## Reproduzir

```bash
cd services/worker
uv run python eval/eval_fretting.py
```

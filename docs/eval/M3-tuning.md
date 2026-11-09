# M3 — Deteção da afinação

- **Data:** 2026-11-09
- **Decisão:** [ADR-0013](../adr/0013-detetar-a-afinacao.md)
- **Código:** `services/worker/src/tabforge_worker/arrange/tuning.py`; avaliação em `services/worker/eval/eval_tuning.py`
- Dados: GuitarSet (360 faixas, tocadas em E standard).

## Como se mede

- **Afinações simuladas:** cada faixa é tocada nas 11 afinações candidatas. Mantêm-se a corda e o traste de cada nota anotada e mudam-se as cordas soltas. Mede a regra de decisão, sem áudio.
- **Falsos alarmes:** as gravações em E standard (microfone e captador, 240) passam pelo Basic Pitch. Cada resultado que não seja E standard é um falso alarme.

## Resultados

`uv run python eval/eval_tuning.py`:

| Afinação | Todas as faixas: exata | Faixas que tocam a corda grave solta (14): exata | Corda grave certa |
|---|---|---|---|
| E standard | 100 % | 100 % | 100 % |
| Eb standard | 3,9 % | 100 % | 100 % |
| D / C# / C / B standard | 3,3 % | 85,7 % | 100 % |
| Drop D / C# / C / B | 3,6 % | 92,9 % | 100 % |
| Drop A | 7,8 % | 100 % | 100 % |
| Todas | 12,7 % | 92,2 % | 100 % |

- Quase todo o GuitarSet (jazz, bossa, funk, rock, cantautor) raramente desce à corda grave solta. Tocadas mais abaixo, essas faixas continuam a caber em E standard, e nada nas notas revela a afinação. Por isso a coluna "todas as faixas" é baixa e a regra fica em E standard.
- Quando a música toca a corda grave, a corda grave sai sempre certa. Os erros que sobram trocam o standard pelo drop.

`uv run --extra ml python eval/eval_tuning.py --transcribed --limit 120`:

| Limiar do chão | Falsos alarmes (240 gravações) | Corda grave certa nas faixas afinadas abaixo (140) |
|---|---|---|
| 3 %, mín. 12 | 3 | 140 |
| **4 %, mín. 12 (escolhido)** | **1** | **140** |
| 5 %, mín. 12 | 0 | 112 |
| 3 %, mín. 20 | 0 | 82 |

- Notas abaixo de Mi2 por gravação em E standard: mediana 0 %, máximo 7,4 % (erros de oitava do Basic Pitch).

`--margins` (standard vs drop, nas faixas tocadas em D standard e em Drop D):

| Margem | D standard lidas como Drop D | Drop D lidas como Drop D |
|---|---|---|
| 0 | 59 % | 81 % |
| **0,05 (escolhida)** | **47 %** | **68 %** |
| 0,10 | 32 % | 50 % |

- A distinção é fraca: as faixas do GuitarSet foram pensadas para E standard e não têm os acordes de um dedo típicos do drop.

## Por medir

- Músicas reais afinadas abaixo e misturas com banda (o baixo que passe pelo Demucs pode baixar o chão): com as tabs certas do utilizador, a comparação mostra se a afinação detetada coincide.

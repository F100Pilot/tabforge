# M3 — Deteção de notas: limpeza e banda

- **Data:** 2026-11-09
- **Código:** `services/worker/src/tabforge_worker/arrange/clean.py` (limpeza, ligada no `RealPipeline`), `eval/eval_band.py` (banda)
- Métrica: note F1 só com o ataque (`mir_eval`: ataque ±50 ms, pitch ±50 cents), média por faixa.

## Limpeza das notas fracas

- Uma nota transcrita fica quando a velocidade (amplitude do Basic Pitch) é pelo menos 0,7 da mediana das notas que começam nos 10 s à volta. Assim, uma introdução calma é comparada consigo mesma.
- Limiar escolhido nos guitarristas 00–02 do GuitarSet e medido nos 03–05 (transcrições Basic Pitch do microfone e do captador, 240 gravações):

| Guitarristas | P | R | F1 |
|---|---|---|---|
| 03–05, sem limpeza | 0,767 | 0,816 | 0,777 |
| **03–05, com limpeza** | **0,827** | **0,798** | **0,800** |
| 00–02, sem → com | 0,744 → 0,831 | 0,801 → 0,774 | 0,761 → 0,792 |

- O filtro de harmónicos (oitava, 12.ª e 15.ª abaixo de uma nota mais forte que soa) acrescentava só +0,001 e ficou de fora.

## Guitarra com banda (BabySlakh)

- BabySlakh (Zenodo 4603870, CC BY 4.0): 20 temas gerados a partir de MIDI (16 kHz), 81 min, todos com guitarra; referência = notas de todas as pistas de guitarra (25 228).
- O Slakh entra no treino do Basic Pitch (ver M0): os valores são um limite superior para a transcrição.

`uv run --extra ml --extra eval python eval/eval_band.py`:

| Condição | P | R | F1 | Notas |
|---|---|---|---|---|
| Só as guitarras (sem banda) | 0,628 | 0,610 | 0,602 | 19 855 |
| Mistura → Demucs (guitarra) → Basic Pitch | 0,217 | 0,275 | 0,215 | 28 829 |
| … + limpeza | 0,223 | 0,266 | 0,215 | 26 979 |

- A maior perda está na separação, não na transcrição. Em 8 dos 20 temas, a pista "guitar" do Demucs fica 40 a 55 dB abaixo da mistura: a guitarra foi para outra pista. Nesses temas a F1 fica em 0,01 a 0,24, mesmo quando a guitarra limpa dava 0,63 a 0,88.
- Com banda, a limpeza é neutra: tira 6 % das notas, sem mudar a F1.
- Cortar as notas dos momentos em que a pista de guitarra tem pouca energia face à mistura (−25 a −8 dB) também não ajuda: F1 0,218 no melhor caso.

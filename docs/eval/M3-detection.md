# M3 — Limiares do Basic Pitch com a limpeza das notas

- **Data:** 2026-11-11
- **Código:** `services/worker/eval/eval_detection.py` (`uv run --extra ml --extra eval python eval/eval_detection.py`; cerca de 15 min em 4 CPU, a primeira vez mais 4 min para as ativações); decisão no [ADR-0017](../adr/0017-limiares-do-basic-pitch.md)
- Métrica: note F1 só com o ataque (`mir_eval`: ataque ±50 ms, pitch ±50 cents), somada sobre as gravações.
- Gravações: GuitarSet, áudio de microfone (360); BabySlakh, pista "guitar" do Demucs `htdemucs_6s` (20 músicas, a de `eval_band.py`).
- O Basic Pitch corre uma vez por gravação. As ativações (frames de nota e de ataque) ficam em `<data>/eval/activations/`, e cada combinação é aplicada com `model_output_to_notes`, como no `predict()`.

## Grelha

300 combinações:
- ataque 0,3 a 0,7;
- duração (frame) 0,2 a 0,5;
- nota mínima 58, 127,7 e 200 ms;
- rácio da limpeza 0 (sem limpeza), 0,5, 0,6, 0,7 e 0,8.

## Limiares para todos

| | Antes (0,5 · 0,3 · 127,7 ms · 0,7) | Escolhidos (0,5 · 0,4 · 58 ms · 0,7) |
|---|---|---|
| GuitarSet 00–02 (escolha) | 0,760 | 0,779 |
| **GuitarSet 03–05 (teste)** | **0,765** | **0,782** |
| Banda (20 músicas) | 0,278 | 0,283 |

- A nota mínima mais curta encontra notas rápidas que se perdiam. A limpeza (rácio 0,7) tira as notas fracas que ela deixaria passar. No M0, sem a limpeza, a nota mínima de 58 ms sozinha baixava a precisão (0,658).

## Aprender por utilizador (não aplicado)

Por guitarrista dos 03–05, por cima dos limiares escolhidos, deixando uma gravação de fora (a afinação só conta se for melhor nas gravações que não viu, como um perfil aceite ou não):

| Guitarrista | Limiares escolhidos | Afinados por guitarrista |
|---|---|---|
| 03 | 0,791 | 0,791 |
| 04 | 0,750 | 0,765 |
| 05 | 0,809 | 0,819 |

- Com banda, afinar numa música e aplicar nas outras não melhora: 0,278 → 0,274, deixando uma música de fora, a partir dos limiares antigos.
- Afinar e aplicar na mesma música (aprender numa metade, testar na outra) dá cerca de +0,015. Isso só serve para voltar a transcrever uma música de que o utilizador já tem a tab certa.

## Limites

- O GuitarSet e o Slakh estão no treino do Basic Pitch, e o BabySlakh é sintetizado a partir de MIDI. Os números indicam a direção, não o valor nas músicas do utilizador.
- Com banda, a maior perda continua na separação (M3-notes: 0,60 só com as guitarras, 0,21 depois do Demucs).

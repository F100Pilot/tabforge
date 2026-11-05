# M3 — Divisão Lead / Rhythm ("Guitarra com banda")

- **Data:** 2026-11-05
- **Decisão:** [ADR-0010](../adr/0010-pautas-lead-e-rhythm.md), fase 2 (worker)
- **Código:** `services/worker/src/tabforge_worker/arrange/split.py` (regras), `adapters/stereo.py` (medida estéreo), `arrange/tracks.py` (Score v3)
- Os números abaixo vêm de execuções reais **sobre áudio sintético**. A qualidade em músicas reais **ainda não foi medida**.

## O que faz

- Só para `source_kind = "mix"`. A guitarra isolada continua a dar um Score v2, igual ao de antes.
- O Demucs dá um só stem de guitarra. As notas que o Basic Pitch transcreve desse stem são divididas em Lead e Rhythm. Depois, cada pista passa pela cadeia do M2 (quantização → Viterbi → layout).
- As duas pistas usam a mesma grelha de batidas. O compasso 1 e o tempo são os mesmos, e a pista mais curta é completada com pausas até as duas terem o mesmo número de compassos.
- Resultado: Score v3 com as pistas `"Lead"` e `"Rhythm"`, por esta ordem. Uma pista sem notas sai só com pausas e não gera aviso, porque os códigos de aviso são só para notas que não foi possível colocar.
- O stem do Demucs é gravado com os canais do modelo (2 no `htdemucs_6s`, confirmado no código do `demucs` 4.1.0: `save_audio` → `encode_wav` grava `[C, T]`). A entrada é normalizada para estéreo. O Basic Pitch lê o mesmo ficheiro em mono (`librosa.load(..., mono=True)`).

## Características por nota

| Característica | Como se mede |
|---|---|
| `side_ratio` | Energia de side, (L−R)/2, sobre a energia total, mid (L+R)/2 mais side. Medida em bandas de ±½ meio-tom à volta da fundamental e das 2 primeiras harmónicas, em janelas de 4096 amostras (hop 1024, Hann), do início da nota até 0,5 s. Vai de 0 (ao centro) a 0,5 (encostada a um lado, ou duas tomadas diferentes abertas L/R). Passa de 0,5 quando há conteúdo em oposição de fase. |
| `polyphony` | Número de notas na mesma forma de acorde: ataques a menos de 50 ms uns dos outros e empilhados com intervalos de, no máximo, uma quinta (7 meios-tons). Uma nota de solo mais de uma quinta acima do acorde fica de fora. |
| `pitch` | Nota MIDI. |
| `repeats` | Quantas vezes a mesma nota volta a ser atacada até 1 s antes ou depois. |
| `duration_s` | Fica registada mas não entra na pontuação, porque os offsets do Basic Pitch não são fiáveis (F1 com offset de 0,55 no M0). |

## Pontuação (positiva → Rhythm, negativa → Lead)

| Regra | Constante | Valor |
|---|---|---|
| Side ratio em escala linear de −1 a +1: 0 em `SIDE_NEUTRAL`, ±1 a ±`SIDE_SPAN` desse ponto | `SIDE_NEUTRAL`, `SIDE_SPAN`, `W_SIDE` | 0,2; 0,2; 1,0 |
| Forma de acorde (2 ou mais notas) | `W_CHORD` | +1,0 |
| Nota única a partir de Mi4 | `LEAD_PITCH`, `W_HIGH` | 64; −1,0 |
| Abaixo de Sol3 (as 3 cordas graves) | `LOW_PITCH`, `W_LOW` | 55; +0,5 |
| … e repetida (2 ou mais vezes em ±1 s) | `REPEAT_MIN`, `REPEAT_WINDOW_S`, `W_REPEAT` | 2; 1,0 s; +0,5 |
| Uníssono: nota única abaixo de Mi4 com side ratio entre 0,12 e 0,32 (solo ao centro e rítmicas dos lados a tocar o mesmo) | `UNISON_LOW`, `UNISON_HIGH` | pontuação 0 |

- **Suavização:** cada nota fica com a média das pontuações das notas do seu meio-compasso, que conta 1, e dos meios-compassos vizinhos, que contam 0,5. O meio-compasso tem 2 batidas da grelha do beat tracker. Só entram notas a uma quinta ou menos de distância. As notas da mesma forma de acorde ficam com o mesmo papel. Constantes: `BEATS_PER_SEGMENT = 2`, `NEIGHBOUR_SEGMENT_WEIGHT = 0,5` e `SMOOTH_PITCH_RANGE = 7`.
- **Decisão:** média ≥ 0,35 → Rhythm; ≤ −0,35 → Lead; entre os dois valores → **as duas pautas** (`BOTH_MARGIN`).
- **Sem estéreo útil** (stem mono, canais iguais no ficheiro todo, ou o percentil 90 do side ratio abaixo de 0,05): a regra de side e a de uníssono saem, e ficam só as regras de papel.

Todos os valores são escolhas iniciais. Só foram verificados no áudio sintético descrito abaixo e devem ser afinados com as tabs de referência do utilizador (comparação por pista).

## Resultados em áudio sintético

Teste `tests/test_lead_rhythm_ml.py` (`uv run --no-sync pytest -m ml -s`). A cadeia é real: Basic Pitch ONNX → beats do librosa → medida estéreo → regras → Score v3.

**1. Power chords dobrados + melodia ao centro.** São 8 compassos a 120 bpm. Os power chords (fundamental, quinta e oitava: Mi2, Lá2, Sol2, Ré2) são tocados em colcheias por duas tomadas, uma encostada à esquerda e outra à direita, com 10 ms de diferença, +7 cents e fase diferente. A melodia (Ré5 a Si5, 13 notas) está ao centro, nos compassos 3–4 e 7–8, por cima dos acordes.

| | Encontradas pelo Basic Pitch | Rhythm | Lead | Ambas |
|---|---|---|---|---|
| Notas dos acordes | 171 / 192 | 171 | 0 | 0 |
| Notas da melodia | 13 / 13 | 0 | 13 | 0 |
| Outras (harmónicas, notas a mais) | 76 | 48 | 19 | 9 |
| Sem estéreo: acordes | 171 | 171 | 0 | 0 |
| Sem estéreo: melodia | 13 | 0 | 12 | 1 |

Mediana do side ratio: 0,489 nos acordes e 0,000 na melodia.

**2. Riff em uníssono.** Um riff grave de notas únicas (Mi2–Si2, colcheias, 4 compassos), tocado pelas duas tomadas rítmicas L/R e por uma terceira guitarra ao centro. As 32 notas do riff foram todas encontradas e as 32 foram para **as duas pautas**. Mediana do side ratio: 0,230.

**Testes unitários da medida estéreo** (`tests/test_stereo.py`, sinais com numpy):

| Sinal | Side ratio |
|---|---|
| Lá4 ao centro, com outra nota só à esquerda | ≈ 0,000 |
| Mi3 em duas tomadas L/R (+6 cents, fase diferente) | 0,698 |
| Lá3 só à esquerda | 0,500 |
| Lá5 ao centro e Mi2 dobrado L/R em simultâneo | 0,000 (Lá5) e 0,498 (Mi2) |

## Limitações e o que falta verificar

- **Sem medição em músicas reais.** O áudio sintético é limpo, sem distorção, reverb nem bleed do Demucs. Nesse áudio a separação é fácil, por isso os números acima mostram que as regras e a cadeia funcionam. Não são uma estimativa de qualidade.
- **Demucs em mistura com banda:** não foi corrido neste trabalho. O stem real vai ter reverb estéreo, bleed de outras fontes e artefactos, e isso muda os side ratios.
- Uma guitarra só, aberta a meio para um lado (por exemplo 70% à esquerda), cai na faixa de uníssono e é copiada para as duas pautas.
- Rítmica e solo no mesmo registo e na mesma posição estéreo (por exemplo, duas guitarras ao centro) não se distinguem pelo estéreo. Aí só contam as regras de papel.
- Um solo com double stops ou acordes vai para Rhythm, e uma rítmica de notas únicas agudas (arpejos) vai para Lead.
- As harmónicas que o Basic Pitch transcreve como notas a mais seguem as regras como qualquer outra nota. No teste 1, 19 delas foram para Lead.

## Reproduzir

```bash
cd services/worker
uv sync --frozen --extra ml
uv run --no-sync pytest -q -m ml -s tests/test_lead_rhythm_ml.py tests/test_stereo.py
```

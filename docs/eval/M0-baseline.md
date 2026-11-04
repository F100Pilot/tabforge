# M0 — Baseline de qualidade (Demucs + Basic Pitch ONNX no GuitarSet)

- **Data:** 2026-11-04
- **Estado:** Basic Pitch medido no GuitarSet completo; Demucs medido em guitarra isolada (subconjunto de 120 faixas). **Mistura com banda não medida** (o GuitarSet não tem; BabySlakh por decidir).
- Todos os números vêm de execuções reais (`data/eval/m0-*.json`, fora do git). Nenhum valor é estimado.

## Configuração

| Item | Valor |
|---|---|
| Dataset | GuitarSet v1.1.0 (Zenodo 3371780), licença CC BY 4.0 verificada no registo Zenodo |
| Faixas | 360 (180 comp, 180 solo; 5 estilos × 72), 3,05 h de áudio, 62 476 notas de referência |
| Áudio | `audio_mono-mic` (microfone) e `audio_mono-pickup_mix` (pickup hexafónico somado a mono) |
| Transcrição | Basic Pitch 0.4.0, `nmp.onnx`, onnxruntime 1.31.1 (CPUExecutionProvider), sem TensorFlow |
| Separação | Demucs 4.1.0 `htdemucs_6s` (stem `guitar`), pesos safetensors de `huggingface.co/adefossez/HTDemucs-6s`, torch 2.15.0 CPU, `shifts=1` |
| Parâmetros | defaults da biblioteca: onset 0,5, frame 0,3, nota mínima 127,7 ms |
| Métrica | `mir_eval` 0.8.2 `precision_recall_f1_overlap`: onset ±50 ms, pitch ±50 cents; "com offset" = offset dentro de 20% da duração (mín. 50 ms). Média macro por faixa |
| Máquina | Intel Xeon @ 2,80 GHz, 4 vCPU, 15 GiB RAM, **sem GPU**; Python 3.13, numpy 2.5.4, librosa 1.0.0 |

## Resultados — note F1 (360 faixas)

| Áudio | P | R | **F1** | P (offset) | R (offset) | **F1 (offset)** | Notas estimadas |
|---|---|---|---|---|---|---|---|
| Microfone | 0,768 | 0,797 | **0,772** | 0,541 | 0,561 | **0,545** | 63 043 |
| Pickup (mix mono) | 0,761 | 0,820 | **0,779** | 0,545 | 0,583 | **0,558** | 67 644 |

Distribuição por faixa (microfone): mediana F1 0,771; percentil 10 0,670; mínimo 0,279.

### Por modo (microfone)

| Modo | Faixas | F1 | F1 (offset) |
|---|---|---|---|
| comp (acordes) | 180 | 0,720 | 0,431 |
| solo (melodia) | 180 | 0,824 | 0,659 |

### Por estilo (microfone)

| Estilo | F1 | F1 (offset) | P | R |
|---|---|---|---|---|
| Bossa Nova (BN) | 0,796 | 0,584 | 0,771 | 0,834 |
| Funk | 0,766 | 0,522 | 0,803 | 0,741 |
| Jazz | 0,779 | 0,570 | 0,792 | 0,783 |
| Rock | 0,774 | 0,551 | 0,784 | 0,785 |
| Singer-Songwriter (SS) | 0,745 | 0,500 | 0,690 | 0,841 |

### Com Demucs `htdemucs_6s` antes do Basic Pitch (microfone, 120 faixas)

Subconjunto `--every 3` (60 comp + 60 solo, 59,7 min de áudio). A linha "sem Demucs" usa as mesmas 120 faixas da execução completa.

| Condição | Faixas | P | R | F1 | F1 (offset) |
|---|---|---|---|---|---|
| sem Demucs | 120 | 0,760 | 0,797 | 0,766 | 0,536 |
| **com Demucs** | 120 | 0,767 | 0,794 | **0,768** | **0,538** |
| sem Demucs — comp | 60 | 0,734 | 0,732 | 0,715 | 0,422 |
| com Demucs — comp | 60 | 0,742 | 0,725 | 0,715 | 0,421 |
| sem Demucs — solo | 60 | 0,787 | 0,862 | 0,818 | 0,650 |
| com Demucs — solo | 60 | 0,792 | 0,864 | 0,821 | 0,654 |

Por faixa, ΔF1 (com − sem): mediana +0,002; melhora em 66 faixas, piora em 45; pior caso −0,052. Em guitarra isolada a separação não degrada nem melhora: é neutra. O ganho do Demucs só se mede em mistura com banda, que este dataset não tem.

### Sensibilidade aos limiares (microfone, 60 faixas)

Subconjunto `--every 6`. Como os ficheiros alternam comp/solo, **as 60 faixas são todas comp**; comparar só entre linhas desta tabela.

| Configuração | P | R | F1 | F1 (offset) |
|---|---|---|---|---|
| default (onset 0,5 · frame 0,3 · min 127,7 ms) | 0,734 | 0,732 | 0,715 | 0,422 |
| onset 0,6 | 0,775 | 0,711 | 0,726 | 0,427 |
| onset 0,4 | 0,675 | 0,738 | 0,685 | 0,403 |
| nota mínima 58 ms | 0,658 | 0,828 | 0,720 | 0,430 |
| frame 0,4 | 0,788 | 0,673 | 0,703 | 0,382 |
| onset 0,6 · frame 0,4 | 0,830 | 0,654 | 0,712 | 0,387 |

Os limiares trocam precisão por recall; o F1 varia no máximo ±0,03. Não são uma alavanca relevante.

## Tempo e memória (CPU, 4 vCPU)

| Medição | Valor |
|---|---|
| Basic Pitch, avaliação completa (3,05 h de áudio) | 1,13 s por minuto de áudio (mic), 1,10 s (pickup) |
| Basic Pitch, clip de 60 s (processo isolado) | carregar 1,19 s; inferir 1,43 s; pico RSS 254 MiB |
| Basic Pitch, clip de 180 s (processo isolado) | carregar 1,43 s; inferir 3,78 s (1,26 s/min); pico RSS 367 MiB |
| Demucs `htdemucs_6s`, avaliação (59,7 min de áudio) | 25,9 s por minuto de áudio; carregar 1,1 s |
| Demucs, clip de 60 s (processo isolado) | carregar 2,4 s; separar 30,0 s; pico RSS 1 677 MiB |
| Demucs, clip de 180 s (processo isolado) | carregar 2,6 s; separar 70,8 s (23,6 s/min); pico RSS 2 077 MiB |
| Pipeline Demucs + Basic Pitch | cerca de 27 s por minuto de áudio em 4 vCPU, cerca de 20× o Basic Pitch sozinho |
| GPU | **não medido** (sem GPU no ambiente) |

Memória: o Basic Pitch fica em cerca de 190 MiB com o modelo carregado, mais cerca de 57 MiB por minuto de áudio adicional. O Demucs fica em cerca de 690 MiB com o modelo carregado, mais cerca de 200 MiB por minuto de áudio adicional (diferenças entre 60 s e 180 s).

## Corda/traste

O Basic Pitch só devolve pitch, e a atribuição corda/traste é do M2, por isso não há precisão corda/traste da pipeline. Medi a ambiguidade do problema nas notas de referência (sem áudio):

| Medição (62 476 notas de referência) | Valor |
|---|---|
| Notas com mais de uma posição possível (afinação standard, trastes 0–24) | 95,1% |
| Regra ingénua "traste mais baixo" acerta corda e traste | 45,4% |

## Limitações (importantes para a decisão)

1. **Contaminação treino/teste.** O código de treino do `basic-pitch` 0.4.0 inclui o GuitarSet na mistura de treino (`constants.DATASET_SAMPLING_FREQUENCY`), com divisão aleatória cuja semente do modelo publicado não é conhecida. Parte das 360 faixas foi provavelmente vista em treino, por isso **estes números são um limite superior** para guitarra limpa. O Slakh também está no treino, o que afeta o BabySlakh da mesma forma.
2. **Sem mistura real.** O GuitarSet só tem guitarra solo. A coluna "pickup" é outra captação da mesma guitarra, não uma mistura com banda. O Demucs só foi medido em guitarra isolada.
3. **Demucs em subconjunto** de 120 faixas (1/3 do dataset), por custo de CPU.
4. **Só guitarra acústica**, afinação standard, 6 intérpretes.

## Reproduzir

```bash
cd services/worker
uv sync --extra ml --extra eval
uv run python eval/download_guitarset.py --files annotation.zip audio_mono-mic.zip audio_mono-pickup_mix.zip
uv run python eval/run_m0.py --audio mic
uv run python eval/run_m0.py --audio mix
uv run python eval/run_m0.py --audio mic --separate --every 3 --tag=-sub3
uv run python eval/profile_m0.py --source ../../data/guitarset/audio_mono-mic/00_Rock1-90-C#_comp_mic.wav --durations 60 180 --stages basic_pitch
uv run python eval/profile_m0.py --source ../../data/guitarset/audio_mono-mic/00_Rock1-90-C#_comp_mic.wav --durations 60 180 --stages demucs
```

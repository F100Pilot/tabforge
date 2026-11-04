# ADR-0002 — Pipeline de transcrição e dependências do worker

- **Estado:** Aceite para guitarra isolada (decisão M0, 2026-11-04); mistura com banda pendente de avaliação
- **Data:** 2026-11-04

## Contexto

Transcrever guitarra de uma mistura completa exige: separação de fontes → transcrição polifónica de pitch → quantização rítmica → atribuição corda/traste. As duas últimas não têm solução pronta de qualidade; são o diferencial do produto.

Factos verificados (2026-11-04):
- `basic-pitch` 0.4.0 declara `tensorflow<2.15.1` como dependência obrigatória em Linux/Python ≥ 3.11. Isso força Python 3.11 e arrasta `keras 2.15.0` e `protobuf 4.25.9`, com advisories sem correção nessa linha (pip-audit: >20 entradas).
- O pacote inclui o modelo em ONNX (`saved_models/icassp_2022/nmp.onnx`). Inferência com `onnxruntime`, **sem TensorFlow instalado**, testada com tons sintéticos E4/A4 → notas MIDI 64/69 corretas, em Python 3.11 e em Python 3.13 + numpy 2.
- `basic-pitch` também fixa `resampy<0.4.3`, que importa `pkg_resources` e obriga a `setuptools<81` (vulnerável). `resampy 0.4.3` remove essa dependência; mesmo teste passou.
- `demucs` 4.1.0: MIT, `requires_python >=3.10`. Num lock universal, uma restrição para macOS x86_64 (`torch<2.3`) arrastava `torch 2.2.2` para todas as plataformas (vulnerável: CVE-2025-32434).

## Decisão

- Worker em **Python 3.13** (igual à API), container próprio, só Linux.
- `uv` com:
  - `environments = ["sys_platform == 'linux'"]` → `torch` atual (2.15.0 no lock).
  - `override-dependencies`: TensorFlow nunca instalado; `resampy>=0.4.3`.
  - Mínimo explícito `torch>=2.6`.
- Etapas de terceiros atrás de interfaces (`Separator`, `Transcriber`, `BeatTracker`):
  - Separação: Demucs `htdemucs_6s` (inclui fonte "guitar").
  - Transcrição: Basic Pitch, backend ONNX (`onnxruntime`).
  - Tempo/beats: librosa.
- Etapas próprias, puras e testáveis (TDD):
  - Quantização rítmica para grelha (1/16, tercinas).
  - Atribuição corda/traste por programação dinâmica (Viterbi) com custo = deslocação da mão + span + preferência de cordas soltas; restrição de uma nota por corda por instante.
- Formato interno: score JSON versionado (schema), convertido para alphaTex/Guitar Pro na exportação.
- CI corre `pip-audit --strict` sobre o lock completo, incluindo extras ML.

## Consequências

- (+) Um único Python em todo o backend; sem TensorFlow (imagem menor, sem advisories de keras/protobuf). Audit do lock: 0 vulnerabilidades conhecidas.
- (+) Modelos substituíveis sem tocar no domínio; domínio testável sem GPU.
- (−) Os overrides contrariam restrições declaradas pelo `basic-pitch`. Mitigação: teste de integração `tests/test_basic_pitch_onnx.py` (`pytest -m ml`, workflow `ml.yml`) que corre inferência ONNX real num clip sintético (E4→64, A4→69) e verifica que o TensorFlow não está instalado. Implementado no M0.
- (−) `basic-pitch` sem release desde 0.4.0 → risco de abandono; avaliar alternativas em M0.
- (−) Separação de guitarra do Demucs 6s é de qualidade moderada; mitigado aceitando upload de stem isolada.
- (−) `uv lock` preserva versões já fixadas: correr `uv lock --upgrade` periodicamente (Dependabot cobre PRs).
- Não verificado ainda: Demucs em mistura com banda, consumo em GPU, execução dentro da imagem Docker do worker, licença dos pesos pré-treinados (o model card não declara licença). Registar em `docs/THIRD_PARTY.md`.

## Resultados do M0 (2026-11-04)

Detalhe e reprodução em [`docs/eval/M0-baseline.md`](../eval/M0-baseline.md).

- Basic Pitch ONNX no GuitarSet (360 faixas, áudio de microfone): note F1 **0,772** (onset ±50 ms) e **0,545** com offset. Comp 0,720 / 0,431; solo 0,824 / 0,659.
- CPU (4 vCPU, sem GPU): 1,1–1,4 s por minuto de áudio; pico de RSS 254 MiB (60 s) e 367 MiB (180 s).
- Os limiares do Basic Pitch movem o F1 no máximo ±0,03. Não compensam afinação.
- Corda/traste: 95,1% das notas de referência têm mais de uma posição possível; a regra "traste mais baixo" acerta 45,4%. Confirma que a atribuição (Viterbi, M2) é o diferencial.
- O Basic Pitch foi treinado com GuitarSet (e Slakh): os números são um limite superior e não servem como estimativa de generalização.
- Demucs `htdemucs_6s` em guitarra isolada (120 faixas): F1 0,768 com Demucs vs 0,766 sem, ou seja, neutro. Custo em CPU de 24–30 s por minuto de áudio (cerca de 20× o Basic Pitch) e pico de RSS de 1,7–2,1 GiB. Pesos carregados em safetensors a partir do Hugging Face.
- Mistura com banda: não medida.

Conclusões:
- O backend ONNX funciona em Python 3.13 sem TensorFlow, em todo o dataset, com custo de CPU baixo. A decisão de dependências mantém-se.
- Onsets e pitch dão um rascunho utilizável para guitarra isolada. Offsets e durações não (F1 0,55; 0,43 em acordes): a quantização rítmica (M2) não pode depender de offsets do Basic Pitch.
- Correr o Demucs sobre uma stem já isolada não traz ganho e custa cerca de 20× mais CPU. A pipeline deve saltar a separação quando o utilizador faz upload de guitarra isolada.
- A decisão go/no-go para áudio em mistura fica pendente de um set de avaliação com banda e fora do treino do Basic Pitch.

### Decisão M0 (2026-11-04, aprovada pelo dono do produto)

- **Go para guitarra isolada.** A pipeline Basic Pitch ONNX segue para o M1/M2 como está. Quando o input é uma stem isolada, não se corre o Demucs.
- **Mistura com banda:** a avaliação faz-se com gravações próprias (não com BabySlakh, que está no treino do Basic Pitch e é 16 kHz). Até haver números, o upload de mistura não é prometido como funcionalidade de qualidade.
- O set de gravações próprias serve também de avaliação fora do treino do Basic Pitch para a guitarra isolada.

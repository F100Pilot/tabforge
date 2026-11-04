# ADR-0002 — Pipeline de transcrição e dependências do worker

- **Estado:** Proposto
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
- (−) Os overrides contrariam restrições declaradas pelo `basic-pitch`. Mitigação: teste de integração (M1) que corre inferência ONNX real num clip sintético e falha se o comportamento mudar.
- (−) `basic-pitch` sem release desde 0.4.0 → risco de abandono; avaliar alternativas em M0.
- (−) Separação de guitarra do Demucs 6s é de qualidade moderada; mitigado aceitando upload de stem isolada.
- (−) `uv lock` preserva versões já fixadas: correr `uv lock --upgrade` periodicamente (Dependabot cobre PRs).
- Não verificado ainda: execução real do Demucs no container, consumo de memória/GPU, licença dos pesos pré-treinados → M0. Registar em `docs/THIRD_PARTY.md`.

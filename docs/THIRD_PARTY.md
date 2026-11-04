# Componentes de terceiros

| Componente | Versão | Licença | Verificado | Notas |
|---|---|---|---|---|
| alphaTab (`@coderline/alphatab`) | 1.9.0 | MPL-2.0 | npm, 2026-11-04 | Copyleft ao nível do ficheiro: modificações aos ficheiros do alphaTab têm de ser publicadas |
| Bravura (fonte musical, incluída no alphaTab) | — | SIL OFL 1.1 | `Bravura-OFL.txt` no pacote, 2026-11-04 | Servida em `/alphatab/font/` com o ficheiro de licença |
| Sonivox (soundfont, incluída no alphaTab) | — | Apache-2.0 | `soundfont/LICENSE` no pacote, 2026-11-04 | Servida em `/alphatab/soundfont/` com o ficheiro de licença |
| Demucs | 4.1.0 | MIT (código) | PyPI, 2026-11-04 | Pesos `htdemucs_6s` em `huggingface.co/adefossez/HTDemucs-6s` (safetensors): **o model card não declara licença**; confirmar com o autor antes de produção |
| Basic Pitch | 0.4.0 | Apache-2.0 | `LICENSE` no wheel, 2026-11-04 | Usado com backend ONNX (`nmp.onnx`, incluído no wheel); TF excluído (ADR-0002) |
| PyTorch | 2.15.0 | BSD-3-Clause | Por verificar | Mínimo `>=2.6` (CVE-2025-32434) |
| ONNX Runtime | 1.31.1 | MIT | metadata do wheel, 2026-11-04 | |
| mir_eval | 0.8.2 | MIT | PyPI, 2026-11-04 | Só avaliação (extra `eval`) |
| GuitarSet | Zenodo 3371780 (versão por confirmar) | Código: MIT; **dados: por verificar** | GitHub, 2026-11-04 | Só avaliação; não redistribuído. `download_guitarset.py` exige `cc-by-4.0` no registo Zenodo |
| FastAPI | 0.162.x | Por verificar | — | |
| Next.js | 16.4.5 | Por verificar | — | |

Antes de produção: confirmar todas as entradas "Por verificar" (ex.: `pip-licenses`, `pnpm licenses list`).

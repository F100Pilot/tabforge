# ADR-0005 — Pacote partilhado do score e Score v2

- **Estado:** Aceite
- **Data:** 2026-11-04

## Contexto

- No M1 o formato do score (`Score`) e a conversão para alphaTex viviam na API. O worker escrevia um score fixo, sem validação do seu lado.
- No M2 o worker passa a gerar scores reais (quantização + corda/traste). Dois modelos do mesmo contrato, um em cada serviço, divergem com o tempo.
- O v1 só tinha durações simples. A quantização real precisa de notas pontuadas, tercinas e ligaduras (notas que atravessam a barra de compasso), e a US-02 pede que notas impossíveis de tocar fiquem marcadas.

## Opções consideradas

1. **Pacote Python partilhado `packages/score`** (dependência por caminho via `uv`) — escolhida.
2. Duplicar o modelo no worker com um teste de contrato no CI — duas cópias para manter.
3. Validar só na API — erros do worker só aparecem quando alguém abre a tab.

## Decisão

- `packages/score` (`tabforge-score`): modelo pydantic do score e `to_alphatex`, sem I/O; dependência de `services/api` e `services/worker` (`[tool.uv.sources]` com `path`).
- Score **v2**: `dots` (0/1) e `tuplet` (3) por beat, `tie` por nota, `warnings` por score (`out_of_range`, `too_many_notes`, com compasso e pitch). Validação: compassos completos, tercinas em grupos de três beats iguais, ligadura só a continuar a mesma corda e traste.
- Documentos v1 continuam válidos (os campos novos têm valores por defeito); o mesmo modelo lê os dois.
- alphaTex: `{d}`, `{tu 3}` e `-` no lugar do traste para ligaduras, verificados no parser do alphaTab 1.9.0.
- Imagens Docker construídas a partir da raiz do repositório (`docker build -f services/<svc>/Dockerfile .`), com `.dockerignore` a excluir `data/`, `node_modules` e ambientes virtuais.

## Consequências

- (+) Um só contrato; o worker valida o que escreve e a API valida o que lê.
- (+) O CI corre lint/mypy/testes do pacote como projeto próprio.
- (−) O contexto de build Docker passa a ser o repositório inteiro (mitigado pelo `.dockerignore`).
- (−) Uma alteração ao pacote pede `uv lock` nos dois serviços.

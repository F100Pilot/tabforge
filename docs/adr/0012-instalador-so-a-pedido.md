# ADR-0012 — Instalador Windows só a pedido; em cada push testa-se o start.bat

- **Estado:** Aceite; alterado pelo [ADR-0015](0015-ci-so-quando-faz-falta.md) (o smoke test só corre quando mudam o launcher ou as dependências)
- **Data:** 2026-11-05
- **Substitui:** a linha "CI" do ADR-0008 (o resto do ADR-0008 mantém-se)

## Contexto

- O ADR-0008 pôs o CI a construir `TabForge-Setup.exe` e a testar o programa empacotado em cada push (cerca de 20 minutos).
- O utilizador corre o TabForge com o `start.bat` (código fonte + `git pull`), não com o instalador, e pediu para não gerar o `.exe` sempre.
- O workflow compilava a interface duas vezes: num passo próprio e de novo dentro do `start.bat`, que prepara sozinho o ambiente Python, as transferências, os pesos do Demucs e a interface.

## Decisão

- **Em cada push para `main` (e PRs):** o job Windows só corre `start.bat --smoke`, que é o caminho usado no PC.
- **A pedido** ("Run workflow", `workflow_dispatch`): depois do mesmo smoke test, PyInstaller, smoke test do programa empacotado, Inno Setup e artefacto `TabForge-Setup.exe`. O bundle usado pelo PyInstaller é o que o `start.bat` preparou.

## Consequências

- (+) CI do Windows mais rápido em cada push e sem compilar a interface duas vezes.
- (+) O que se testa sempre é exatamente o que o utilizador corre.
- (−) Uma regressão só do empacotamento (PyInstaller/Inno Setup) só aparece quando se pede o instalador.

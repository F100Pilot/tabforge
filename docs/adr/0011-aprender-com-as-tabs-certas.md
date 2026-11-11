# ADR-0011 — Aprender a escolha de corda/traste com as tabs certas e as correções

- **Estado:** Aceite; alterado pelo [ADR-0016](0016-aprender-com-uma-tab-e-refazer-posicoes.md) (mínimo de 1 tab, validação por metades com 1 ou 2 tabs, refazer as posições de tabs existentes)
- **Data:** 2026-11-05

## Contexto

- A escolha de corda e traste (Viterbi, `services/worker/arrange/fretting.py`) usa 4 pesos (`span`, `height`, `move`, `open_move`) afinados uma vez no GuitarSet (M2: 65,7 % de posições exatas em guitaristas de teste).
- O utilizador quer que o algoritmo aprenda com as tabs certas que importa (ADR-0009) e com as correções que aplica ou faz no editor.
- Cada tab certa dá, para cada nota, o pitch e a posição certa. Para afinar a escolha de posição não é preciso áudio: basta voltar a correr o Viterbi sobre os pitches da tab certa e medir quantas posições coincidem.

## Opções consideradas

1. **Afinar os 4 pesos por utilizador**, por pesquisa em grelha sobre as tabs certas e as revisões corrigidas, e aplicar só se melhorar em validação cruzada por tab — escolhida.
2. Treinar um modelo (rede neuronal) de posições — precisa de muito mais dados do que um utilizador junta; menos explicável.
3. Afinar pesos globais para todos — não reflete o estilo de cada guitarrista.

## Decisão

- **Dados de treino de cada utilizador**, um conjunto de notas por tab: as notas da tab certa (todas as pistas com referência). Se a tab não tiver referência, as notas da última revisão editada pelo utilizador (`source = user`), quando é diferente da revisão da IA. Os eventos são as notas com o mesmo início (acordes).
- **Afinação no worker** (que tem o Viterbi):
  - pesquisa em grelha dos 4 pesos;
  - medida = posições exatas sobre todas as notas de treino;
  - com 3 ou mais tabs, validação cruzada "deixar uma tab de fora", e os pesos só são aceites se a média em validação for melhor que a dos pesos por omissão;
  - com menos de 200 notas ou menos de 2 tabs não se afina (dados insuficientes).
- **Quando:** a API marca o perfil como "por atualizar" quando se guarda uma tab certa, quando se aplicam correções e quando se guarda uma revisão editada. O worker atualiza os perfis marcados no ciclo dele, e o utilizador também pode pedir "Atualizar agora".
- **Perfil** (`fretting_profiles`, um por utilizador, apagado com a conta): pesos aceites, precisão com os pesos por omissão e com os afinados, número de tabs e notas, estado e data.
- **Uso:** os jobs novos desse utilizador usam os pesos do perfil quando foram aceites; senão, os pesos por omissão. As tabs já geradas não mudam sozinhas.
- **UI:** um cartão "Aprendizagem" mostra com quantas tabs e notas o TabForge aprendeu, a precisão antes e depois e se os pesos estão em uso, com o botão "Atualizar agora".

## Consequências

- (+) Aprendizagem explicável e reversível: 4 números por utilizador, com a medida que os justificou.
- (+) Não precisa de áudio nem de GPU; corre em segundos.
- (−) Só aprende a escolha de corda/traste. O ritmo (quantização), a deteção de notas e a divisão Lead/Rhythm ficam para depois.
- (−) Com poucas tabs a melhoria pode ser pequena ou nula; nesse caso os pesos por omissão continuam em uso e a UI diz porquê.

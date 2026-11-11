# ADR-0016 — Aprender com uma tab certa e refazer as posições de uma tab existente

- **Estado:** Aceite
- **Data:** 2026-11-11
- **Substitui:** do ADR-0011, o mínimo de 2 tabs, a comparação "no próprio conjunto" com 2 tabs e "as tabs já geradas não mudam sozinhas" (o resto do ADR-0011 mantém-se)

## Contexto

- Com o ADR-0011 a aprendizagem só começa com 2 tabs certas; o utilizador tem 1 (336 notas) e não vê efeito nenhum.
- Mesmo com pesos aceites, só os jobs novos os usam: o utilizador não consegue ver o que mudou na tab que comparou.
- Com 2 tabs o ADR-0011 aceitava pesos medidos nas próprias notas de treino, que dão sempre um resultado igual ou melhor do que os pesos por omissão.

## Decisão

- **Mínimo:** 1 tab e 200 notas.
- **Validação com 1 ou 2 tabs:** cada pista divide-se em duas metades no tempo (eventos da primeira metade e da segunda). Cada metade é colocada com os pesos que são melhores nas outras partes (as outras metades, das mesmas e das outras tabs), como na validação cruzada "deixar uma tab de fora". Os pesos só são aceites se essa precisão for maior que a dos pesos por omissão. Com 3 ou mais tabs fica a validação por tab do ADR-0011.
- **Refazer as posições** (`POST /v1/tabs/{id}/refret`): volta a escolher corda e traste das notas da revisão atual (todas as pistas, cada uma com a sua afinação) com os pesos aprendidos, sem áudio, e grava uma revisão nova. Só com pesos em uso. As notas ligadas (`tie`) seguem a nota onde começam; se uma escolha nova pusesse duas notas na mesma corda, esses eventos ficam como estavam.
- **Origem da revisão:** `learned` (nova). A aprendizagem continua a ler só revisões `user`, para não aprender com o próprio resultado.
- **Onde corre:** na API, no pedido (o Viterbi demora milissegundos). Para isso o Viterbi (`fretting`) passa do worker para o pacote partilhado `tabforge-score` (ADR-0005); o worker usa-o de lá.

## Consequências

- (+) A aprendizagem começa com a primeira tab certa, e o utilizador vê o efeito numa tab que já tem e pode comparar outra vez.
- (+) A validação por metades mede os pesos em notas que não serviram para os escolher.
- (−) Com 1 tab, os pesos refletem uma música só; a validação por metades evita aceitar pesos que só decoram essa música, mas a melhoria pode não se repetir noutras.
- (−) O pacote partilhado passa a ter também a escolha de posições, não só o formato da pauta.

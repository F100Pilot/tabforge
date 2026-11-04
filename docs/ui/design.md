# Interface — decisões de design (aprovadas a 2026-11-04)

Wireframes e protótipo: canvas "Wireframes TabForge" (claude.ai, privado do dono do produto). Este ficheiro é a fonte de verdade para a implementação do M2.

## Decisões

| Tema | Decisão |
|---|---|
| Direção | Interface escura, shell de aplicação com navegação lateral (empilha em ecrãs estreitos) |
| Cor da marca | Âmbar `#F2B544` (texto sobre âmbar: `#1A1407`), só em ações principais e estado ativo |
| Tipografia | Geist (UI) e Geist Mono (tempos, números), Google Fonts |
| Pauta | Render do alphaTab 1.9; tema da pauta claro/escuro à escolha do utilizador, por defeito segue a interface (escuro) |
| Leitor | Barra flutuante sobre a pauta: play/stop, posição, velocidade 25–150%, repetir secção, metrónomo |
| Editor | Inspetor flutuante junto à nota selecionada (corda, traste, "mesma nota noutra posição"); durações numa barra no cabeçalho; atalhos de teclado; revisões numa linha temporal |
| Expectativa de qualidade | Etiqueta "Rascunho IA · verifique ritmo e posições" (M0: notas F1 0,77, durações 0,55) |
| Upload | "Só a guitarra" por defeito (salta separação, ADR-0002); "Guitarra com banda" marcada como em avaliação |

## Tokens

Interface (escura):

| Token | Valor | Uso |
|---|---|---|
| `bg` | `#0F1115` | Fundo da app |
| `panel` | `#171A20` | Cartões, painéis |
| `panel-2` | `#1E222A` | Chips, item ativo |
| `line` | `#22262E` / `#2A2F38` | Bordas |
| `text` | `#ECEEF1` | Texto principal |
| `muted` | `#9AA1AC` | Texto secundário |
| `accent` | `#F2B544` | Ações principais |
| `ok` / `info` / `error` | `#4CC38A` / `#7FB2FF` / `#F2866C` | Estados (com texto, nunca só cor) |

Pauta (alphaTab `display.resources`):

| Recurso | Escura | Clara |
|---|---|---|
| fundo do cartão | `#14171C` | `#FAFAF7` |
| `mainGlyphColor` | `#E6E8EB` | `#1B1D21` |
| `secondaryGlyphColor` | `#9AA1AC` | `#6B7079` |
| `staffLineColor` | `#4A505B` | `#A3A39B` |
| `barSeparatorColor` | `#8A919C` | `#4A4E55` |
| `barNumberColor` | `#F2B544` | `#9A6A12` |
| `scoreInfoColor` | `#C9CED6` | `#1B1D21` |

## Acessibilidade (WCAG 2.1 AA)

- Alvos de toque ≥ 44 px; foco visível; controlos reais (`button`, `input`, `label`).
- Contraste de texto ≥ 4,5:1 sobre `bg` e `panel`; estados com texto além da cor.
- Elementos de ícone com `aria-label`; estado do leitor e do job em `aria-live`.

## Por decidir

- Tema claro para toda a interface (hoje só a pauta tem tema claro).
- Confiança por nota ("a verificar"): requer que o worker guarde uma medida de confiança; método por validar.

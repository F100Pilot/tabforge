# ADR-0013 — Detetar a afinação da guitarra a partir das notas transcritas

- **Estado:** Aceite
- **Data:** 2026-11-09

## Contexto

- O worker escrevia todas as tabs em E standard. Numa música afinada abaixo (B standard, Drop D…), as notas abaixo do Mi grave eram deitadas fora ("N notas não couberam no braço") e as posições não batiam certo com a tab certa (0 % de posições certas na comparação, ADR-0009).
- A comparação já lê a afinação da tab certa e muda a tab ao aplicar as correções. Falta acertar a afinação logo na transcrição, sem tab certa.
- Só há as notas transcritas (Basic Pitch, semitons) e o seu tempo. Não há um modelo aberto e estabelecido que diga a afinação de uma guitarra a partir do áudio.

## Opções consideradas

1. **"Chão" das notas graves + esforço do Viterbi para standard vs drop** — escolhida.
2. Escolher a afinação em que o Viterbi toca a música com menos esforço, entre todas — medido no GuitarSet: acerta 27 % das afinações (o esforço quase não muda de uma afinação para a seguinte).
3. Perguntar a afinação ao utilizador antes de transcrever — fica possível mais tarde; não resolve as transcrições sem resposta.

## Decisão

- **Candidatas:** E, Eb, D, C#, C e B standard; Drop D, Drop C#, Drop C, Drop B e Drop A (`arrange/tuning.py`).
- **Chão:** a nota com 4 % das notas, e pelo menos 12, nessa altura ou abaixo. Notas abaixo de Lá1 (33) não contam. Escolhe-se a candidata mais alta cuja corda grave chega a esse chão; com o chão em Mi2 ou acima, E standard.
- **Standard ou drop** (mesma corda grave, por exemplo D standard e Drop D): ganha a drop só se o Viterbi a tocar com pelo menos 5 % menos esforço, contando 10 por cada nota que não consegue colocar.
- **Uso:** o pipeline real deteta a afinação antes de arranjar. Lead e Rhythm usam a mesma afinação. O nome da afinação fica na tab. Um `tuning` fixo no `RealPipeline` salta a deteção.
- **Medido** (`docs/eval/M3-tuning.md`):
  - 240 gravações reais do GuitarSet em E standard (Basic Pitch): 1 falso alarme (0,4 %);
  - faixas tocadas noutra afinação e que usam a corda grave solta: corda grave certa em 100 %, afinação exata em 92 %.

## Consequências

- (+) As notas graves de músicas afinadas abaixo passam a ficar na tab, e a afinação vem certa quando a música as toca.
- (+) Sem modelos novos nem dependências; corre em menos de um segundo.
- (−) Uma música afinada abaixo que nunca desce abaixo de Mi2 fica em E standard. As notas cabem todas, mas as posições diferem das do guitarrista. A comparação com a tab certa corrige isto.
- (−) Standard e drop com a mesma corda grave distinguem-se mal (no GuitarSet, 47 % das faixas em D standard seriam lidas como Drop D). A comparação também corrige isto.
- (−) Ainda não medido em misturas com banda: as notas do baixo que escapem ao Demucs podem baixar o chão. O limiar de 4 % foi escolhido para aguentar os erros de oitava do Basic Pitch (até 7,4 % de notas abaixo de Mi2 numa gravação em E standard).

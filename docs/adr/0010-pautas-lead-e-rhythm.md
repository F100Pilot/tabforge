# ADR-0010 — Pautas Lead e Rhythm (Score v3 com pistas)

- **Estado:** Aceite
- **Data:** 2026-11-05

## Contexto

- Em músicas com banda há normalmente duas guitarras com papéis diferentes: Lead (solos, melodias) e Rhythm (riffs, acordes). As tabs de referência (Guitar Pro) trazem-nas como pistas separadas.
- O TabForge gera uma só pauta: o Demucs (`htdemucs_6s`) dá um único stem "guitarra" com as duas misturadas, e o Score v2 tem uma única pista.
- Decisões do utilizador: duas pautas só em "Guitarra com banda" (guitarra isolada continua com uma); num trecho ambíguo (as duas guitarras a tocar o mesmo riff) o trecho aparece nas duas pautas.
- O alphaTab 1.9 lê várias pistas em alphaTex (`\track "Nome"`, `\staff {tabs}`, `\tuning (…)` por pista) — verificado.

## Opções consideradas

1. **Score v3 com pistas + divisão heurística das notas transcritas** (estéreo + papel musical), medida com a comparação por pista — escolhida.
2. Modelo de separação Lead/Rhythm — não há um modelo aberto e estabelecido para isto; fica para reavaliar.
3. Uma só pauta com duas vozes — não corresponde às tabs de referência nem permite editar/exportar cada guitarra.

## Decisão

- **Score v3** (`packages/score`): `{"schema_version": 3, "tempo_bpm", "time_signature", "tracks": [{"name", "tuning", "bars", "warnings"}]}`.
  - 1 a 4 pistas, todas com o mesmo número de compassos; as regras de validação do v2 aplicam-se a cada pista.
  - v1/v2 continuam válidos e são vistos como uma pista ("Guitarra").
  - `to_alphatex` escreve `\track` por pista.
- **API:** revisões e preview aceitam v3. A tab certa passa a ser guardada por pista da tab (`tab_references` único por tab + índice da pista; migração). `GET /v1/tabs/{id}/comparison?track=N` compara essa pista.
- **Web:** o visualizador mostra todas as pistas (escolha da pista visível, como no Guitar Pro). O editor edita a pista escolhida. O export leva todas as pistas, e a comparação faz-se por pista.
- **Worker (só "Guitarra com banda"):** divide as notas do stem de guitarra em Lead e Rhythm com regras explicáveis.
  - Estéreo: guitarras rítmicas dobradas e abertas para os lados têm muita energia "side"; o solo tende a estar ao centro.
  - Papel: acordes/power chords e graves repetidos → Rhythm; linhas de uma nota mais agudas → Lead.
  - Suavização no tempo, para não saltar nota a nota.
  - Trechos sem decisão clara → nas duas pautas.
  - A qualidade é medida com as tabs de referência do utilizador (pista Lead e pista Rhythm) antes de afinar as regras.

## Consequências

- (+) Tabs comparáveis pista a pista com as de referência; editar e exportar cada guitarra.
- (+) Dados antigos continuam válidos sem migração dos documentos.
- (−) Mais código no visualizador/editor (escolha de pista).
- (−) A divisão heurística vai errar em misturas sem separação estéreo e quando as guitarras tocam no mesmo registo; a percentagem só se conhece depois de medir.
- (−) Demucs continua a dar um só stem de guitarra: a separação é das notas transcritas, não do áudio.

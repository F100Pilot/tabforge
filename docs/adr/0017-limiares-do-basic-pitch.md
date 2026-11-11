# ADR-0017 — Limiares do Basic Pitch escolhidos com a limpeza das notas; sem aprendizagem da deteção por utilizador

- **Estado:** Aceite
- **Data:** 2026-11-11

## Contexto

- O worker usava os limiares por omissão do `basic-pitch` 0.4.0 (ataque 0,5, duração 0,3, nota mínima 127,7 ms). No M0 (ADR-0002), cada limiar sozinho movia a F1 no máximo ±0,03 e ficaram os da biblioteca.
- Desde o M3 o worker tira as notas fracas (`arrange.clean`, rácio 0,7), o que muda o equilíbrio entre notas a mais e notas em falta.
- O utilizador pediu para a TabForge aprender a deteção de notas com as tabs certas (fase 2 da aprendizagem). Antes de a construir, mediu-se quanto se ganha.

## Medição

`eval/eval_detection.py` ([M3-detection](../eval/M3-detection.md)): 300 combinações de ataque, duração, nota mínima e rácio de limpeza, aplicadas às ativações do Basic Pitch (o modelo corre uma vez por gravação).

- Escolhida nos guitarristas 00–02 do GuitarSet: ataque 0,5, duração 0,4, nota mínima 58 ms, limpeza 0,7. Nos guitarristas 03–05: F1 0,765 → 0,782. Nas 20 músicas com banda (BabySlakh, Demucs): 0,278 → 0,283.
- Afinar por guitarrista, por cima disso e medido em gravações que não viu: +0,000 a +0,015.
- Afinar por música com banda e usar noutras músicas: não melhora (0,278 → 0,274).

## Decisão

- **Limiares da TabForge:** ataque 0,5, duração 0,4, nota mínima 58 ms (`adapters/basic_pitch.py`); a limpeza fica em 0,7. Valem para as transcrições novas.
- **Sem aprendizagem da deteção por utilizador, por agora:** o ganho medido é pequeno e não passa de uma música com banda para outra, e exigiria guardar as ativações e o ritmo de cada transcrição e afinar com o modelo no worker.
- As perdas maiores com banda estão na separação da guitarra (F1 0,60 só com as guitarras, 0,21 depois do Demucs); é aí que se trabalha a seguir, com as comparações do utilizador em músicas reais.

## Consequências

- (+) Mais notas certas em todas as transcrições novas, sem custo de CPU.
- (+) A decisão de não construir a aprendizagem da deteção está medida e é reproduzível.
- (−) O GuitarSet e o Slakh estão no treino do Basic Pitch e o BabySlakh é sintetizado: os ganhos indicam a direção, não garantem o mesmo nas músicas do utilizador.
- (−) As tabs já geradas não mudam; para usar os limiares novos é preciso transcrever outra vez.

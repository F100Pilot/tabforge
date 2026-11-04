# PRD — TabForge (nome provisório)

Plataforma web de tablaturas interativas (estilo Songsterr) com **geração assistida por IA** a partir de áudio.

- **Tier:** L (multiutilizador, autenticação, uploads de utilizadores, risco de direitos de autor)
- **Estado:** Draft — aguarda aprovação
- **Data:** 2026-11-04

## 1. Problema

- Criar tablaturas à mão é lento (horas por música).
- Ferramentas de transcrição automática existentes produzem notas MIDI, não tablatura tocável (corda + traste, ritmo legível).
- Plataformas como o Songsterr assentam num catálogo licenciado — não geram tabs a partir do áudio do próprio utilizador.

## 2. Personas

| Persona | Necessidade |
|---|---|
| **Guitarrista amador** | Aprender uma música a partir de uma gravação; ver tab sincronizada com playback |
| **Músico/professor** | Transcrever a própria gravação ou de alunos; corrigir e exportar (Guitar Pro / PDF) |
| **Criador de conteúdo** | Produzir tabs das suas composições originais para publicar |

## 3. Objetivos e métricas de sucesso (MVP)

| Objetivo | Métrica | Alvo |
|---|---|---|
| Transcrição útil | Note F1 (onset ±50 ms) num set de avaliação interno de guitarra isolada | ≥ 0,70 (baseline a medir) |
| Tab tocável | % de notas com atribuição corda/traste aceite sem edição (avaliação humana) | ≥ 80% |
| Tempo de processamento | p95 para 4 min de áudio, worker GPU | ≤ 3 min |
| Edição | Tempo médio para corrigir uma tab gerada vs. escrever do zero | −50% |

> Os alvos de qualidade são hipóteses. Primeiro marco técnico: medir a baseline real (ver BACKLOG, M0).

## 4. User stories e critérios de aceitação

### US-01 — Upload de áudio (Must)
Como guitarrista, quero carregar um ficheiro de áudio, para obter uma tab gerada.
- **Given** utilizador autenticado, **When** carrega MP3/WAV/FLAC/OGG ≤ 50 MB e ≤ 10 min, **Then** é criado um job em estado `queued` e o ficheiro fica em storage privado.
- **Given** ficheiro com tipo real (magic bytes) diferente do declarado, **When** carrega, **Then** recebe 415 e nada é guardado.
- **Given** ficheiro > limites, **When** carrega, **Then** recebe 413 com mensagem clara.

### US-02 — Transcrição por IA (Must)
Como guitarrista, quero que o sistema isole a guitarra e gere a tab, para não transcrever à mão.
- **Given** job `queued`, **When** o worker o processa, **Then** passa por `separating → transcribing → arranging → done` e grava a tab.
- **Given** falha em qualquer etapa, **Then** o job fica `failed` com código de erro; o utilizador pode repetir (máx. 3 tentativas).
- **Given** afinação escolhida (default E standard), **Then** todas as notas atribuídas cabem nas cordas/trastes (0–24) dessa afinação, ou são marcadas `unplayable`.

### US-03 — Visualizar e tocar tab (Must)
Como guitarrista, quero ver a tab com cursor sincronizado e playback, para aprender a música.
- **Given** tab `done`, **When** abro a página, **Then** a tab é renderizada (notação + tab) com play/pause, tempo variável (25–150%) e loop de secção.

### US-04 — Editar tab (Must)
Como músico, quero corrigir notas, ritmo e posição, para chegar a uma tab correta.
- **Given** tab própria, **When** altero uma nota e guardo, **Then** é criada uma nova revisão (histórico imutável).

### US-05 — Exportar (Should)
- Exportar para Guitar Pro (.gp) e MIDI; PDF via impressão.

### US-06 — Partilha pública (Could — atrás de política de conteúdo, ver ADR-0003)
- Tabs privadas por defeito. Publicação só com declaração de titularidade/licença; mecanismo de takedown.

### US-07 — Conta (Must)
- Registo/login por email + OAuth (Google). Eliminação de conta remove áudio, tabs e dados pessoais (RGPD art. 17).

## 5. Requisitos não funcionais

- **Segurança:** OWASP ASVS L2; uploads validados por magic bytes; storage privado com URLs pré-assinados de curta duração; rate limiting.
- **Privacidade (RGPD):** áudio original apagado após N dias (configurável, default 30); sem dados pessoais em logs; DPA com fornecedores.
- **Acessibilidade:** WCAG 2.1 AA na UI fora do renderer de pauta.
- **Performance:** API p95 < 300 ms (excluindo uploads); render de tab de 200 compassos < 1 s em desktop médio.
- **Disponibilidade:** 99,5% (MVP).
- **Plataformas:** browsers evergreen desktop + mobile (responsivo).

## 6. Fora de âmbito (MVP)

- Catálogo de músicas comerciais pré-transcritas.
- Baixo, bateria, piano (arquitetura preparada; não implementado).
- Transcrição em tempo real (microfone).
- Apps nativas.
- Pagamentos/subscrições.

## 7. Pressupostos

- Existe GPU disponível para o worker em produção (CPU apenas em dev).
- Modelos open-source (Demucs, Basic Pitch) têm qualidade suficiente para um **rascunho editável**, não para tab final.
- O editor é parte central do valor, não um extra.

## 8. Riscos principais

| Risco | Impacto | Mitigação |
|---|---|---|
| Direitos de autor (tabs de músicas protegidas) | Crítico — legal | ADR-0003: privado por defeito; sem catálogo; takedown; parecer jurídico antes de partilha pública |
| Qualidade da transcrição em mix completa | Alto — produto | Medir baseline cedo (M0); editor forte; permitir upload de stem isolada |
| Custo de GPU | Médio | Fila com limites por utilizador; duração máxima; cache por hash de áudio |
| Dependências ML desatualizadas (Basic Pitch fixa TF < 2.15.1) | Médio | Backend ONNX sem TensorFlow + overrides verificados (ADR-0002) |

## 9. Priorização (MoSCoW) — MVP = Must

- **Must:** US-01, US-02, US-03, US-04, US-07
- **Should:** US-05
- **Could:** US-06
- **Won't (MVP):** catálogo, outros instrumentos, tempo real

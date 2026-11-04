# ADR-0003 — Política de conteúdo e direitos de autor

- **Estado:** Proposto — **requer parecer jurídico antes de ativar partilha pública**
- **Data:** 2026-11-04

## Contexto

Tablaturas de músicas protegidas são obras derivadas; plataformas de tabs já foram alvo de ações de editoras. O Songsterr opera com catálogo licenciado junto de editoras. Este projeto não tem licenças.

## Decisão (MVP)

- Sem catálogo de músicas comerciais.
- Tabs **privadas por defeito**; o utilizador transcreve áudio que carrega para uso pessoal.
- Visibilidade `public` desativada por feature flag até:
  1. parecer jurídico (PT/UE — Diretiva 2019/790, art. 17, se aplicável),
  2. declaração de titularidade/licença no momento da publicação,
  3. processo de notice-and-takedown com audit log.
- Áudio original apagado após período de retenção (default 30 dias).

## Consequências

- (+) Risco legal do MVP fortemente reduzido.
- (−) Sem efeito de rede/SEO de um catálogo público no arranque — o crescimento depende do valor da ferramenta de transcrição + editor.
- Licenciamento (modelo Songsterr) é uma decisão de negócio futura, fora deste ADR.

> Isto não é aconselhamento jurídico.

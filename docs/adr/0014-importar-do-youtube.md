# ADR-0014 — Importar áudio de um link do YouTube (só no desktop)

- **Estado:** Aceite
- **Data:** 2026-11-09
- **Complementa:** ADR-0003 (o utilizador transcreve áudio para uso pessoal) e ADR-0008 (desktop)

## Contexto

- O utilizador quer colar um link do YouTube em vez de procurar o MP3 da música.
- O ADR-0003 só previa áudio que o utilizador carrega, para uso pessoal, sem partilha pública.
- Descarregar do YouTube vai contra os termos do YouTube e o áudio é de terceiros, protegido por direitos de autor. Numa versão online, o TabForge passaria a descarregar e guardar conteúdo de terceiros para muitos utilizadores.

## Opções consideradas

1. **Só no desktop: a API local descarrega com o yt-dlp, converte para MP3 com o ffmpeg do pacote e trata o ficheiro como um upload** — escolhida.
2. No worker, como uma etapa nova do job — mais mudanças (modelo de dados, fila) sem ganho para um só utilizador.
3. Também na versão online — fora de questão sem parecer jurídico (ADR-0003).

## Decisão

- `POST /v1/imports/youtube {url, source_kind}` só existe com `env=desktop` (fora disso, 404).
- Só links `http(s)` para `youtube.com`, `www.`/`m.`/`music.youtube.com` e `youtu.be`, sem credenciais nem porta. Um vídeo de cada vez (`noplaylist`).
- yt-dlp (`yt-dlp[default]`, licença Unlicense) como extra `youtube` da API; o desktop instala-o.
  - Usa o Node do pacote como runtime de JavaScript, que o YouTube exige; os scripts vêm no pacote `yt-dlp-ejs`, sem nada descarregado da internet.
  - A duração é verificada antes de descarregar (máximo de 10 min, como no US-01).
  - O áudio é convertido para MP3 (192 kbps) e verificado: tipo MP3 e tamanho ≤ 50 MB.
- O MP3 entra no armazenamento local como um upload terminado e o job da transcrição fica na fila. Uma cópia fica em `Música\TabForge` (nome a partir do título, sem caracteres proibidos no Windows, sem apagar ficheiros com o mesmo nome).
- **Responsabilidade:** uso pessoal, no PC do utilizador. A versão online não tem esta rota.

## Consequências

- (+) Colar um link e transcrever, sem procurar ficheiros.
- (−) O YouTube muda com frequência e o yt-dlp tem de acompanhar. A versão fica fixa no `uv.lock` e só muda quando a atualizarmos no repositório. Quando a descarga falhar, a mensagem do yt-dlp aparece ao utilizador.
- (−) Não testável no CI contra o YouTube (rede e bloqueios de IPs de centros de dados). O teste automático usa o extrator genérico do yt-dlp com um ficheiro servido localmente, com o ffmpeg real.

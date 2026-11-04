# ADR-0004 — Object storage de desenvolvimento: versitygw em vez de MinIO

- **Estado:** Aceite
- **Data:** 2026-11-04
- **Altera:** ADR-0001 ("MinIO em dev")

## Contexto

- Em 2026-11-04, `minio/minio` já não existe no Docker Hub: o pull devolve "repository does not exist" e a API do Docker Hub responde "object not found". O `docker-compose.yml` original deixou de arrancar.
- `quay.io` está bloqueado na rede deste ambiente de execução; não foi verificado se a MinIO ainda publica lá.
- Requisito real do dev: API S3 com URLs pré-assinados SigV4 que assinem `Content-Type` e `Content-Length` (o upload US-01 depende disso), HEAD, GET com `Range`, DELETE e CORS de bucket.

## Opções consideradas

| Opção | Licença | Notas |
|---|---|---|
| **versitygw** (`versity/versitygw`) | Apache-2.0 | Um binário; backend POSIX; configurável só por env vars (serve como service container no CI) |
| SeaweedFS | Apache-2.0 | Mais componentes (master/volume/filer/s3) e mais config para o mesmo resultado |
| Garage | AGPL-3.0 | Exige definir layout do cluster antes do primeiro uso |
| RustFS | Apache-2.0 | Projeto mais recente |

## Decisão

- Dev e CI usam `versity/versitygw:v1.9.0` com backend POSIX (`VGW_BACKEND=posix`, `VGW_BACKEND_ARG=/data`, volume em `/data`).
- Verificado em 2026-11-04 com boto3: PUT pré-assinado com tamanho e tipo exatos → 200; tamanho ou `Content-Type` diferentes → 403; HEAD, GET com `Range` e DELETE funcionam (`tests/test_storage_s3.py`).
- O código fala só a API S3 (boto3); produção continua em S3 (ADR-0001).
- O bucket e a regra CORS de dev são criados por `python -m tabforge_api.cli init-storage` (serviço `migrate` do compose). Em produção vêm da infraestrutura, não da app.

## Consequências

- (+) O compose volta a arrancar sem imagens descontinuadas; o mesmo servidor S3 corre no CI.
- (+) Sem dependência de código no servidor: trocar de servidor S3 de dev é só mudar o compose.
- (−) versitygw não é o servidor de produção: diferenças de comportamento S3 só aparecem em staging. Mitigação: testes do adapter correm também contra S3 real antes de produção.

# Build from the repository root: docker build -f services/api/Dockerfile .  (ADR-0005)
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
WORKDIR /app/services/api
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY packages/score /app/packages/score
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY services/api/src ./src
COPY services/api/alembic.ini ./
COPY services/api/migrations ./migrations
RUN uv sync --frozen --no-dev
RUN useradd --system --uid 10001 app
USER app
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "tabforge_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

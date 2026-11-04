FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
RUN useradd --system --uid 10001 app
USER app
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "tabforge_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

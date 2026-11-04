# Build from the repository root: docker build -f services/worker/Dockerfile .  (ADR-0005)
# Same Python as the API; basic-pitch runs on ONNX without tensorflow (docs/adr/0002).
FROM python:3.13-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
WORKDIR /app/services/worker
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY packages/score /app/packages/score
COPY services/worker/pyproject.toml services/worker/uv.lock ./
# ML extras enter the image with the real pipeline (M2.2).
RUN uv sync --frozen --no-dev --no-install-project
COPY services/worker/src ./src
RUN uv sync --frozen --no-dev
RUN useradd --system --uid 10001 worker
USER worker
CMD ["uv", "run", "--no-sync", "python", "-m", "tabforge_worker"]

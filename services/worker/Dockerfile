# Same Python as the API; basic-pitch runs on ONNX without tensorflow (docs/adr/0002).
FROM python:3.13-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
# ML extras are installed from M0 onward: add `--extra ml` here.
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
RUN useradd --system --uid 10001 worker
USER worker
# M1: queue loop with stub stages. ML extras (--extra ml) enter the image with the real stages (M2).
CMD ["uv", "run", "--no-sync", "python", "-m", "tabforge_worker"]

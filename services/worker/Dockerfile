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
# Entry point implemented in M1 (queue loop).
CMD ["uv", "run", "--no-sync", "python", "-c", "import tabforge_worker; print('worker skeleton')"]

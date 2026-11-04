# Build from the repository root: docker build -f services/worker/Dockerfile .  (ADR-0005)
# Same Python as the API; basic-pitch runs on ONNX without tensorflow (ADR-0002).
# torch comes with its CUDA libraries: the PRD assumes a GPU worker in production.
FROM python:3.13-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
WORKDIR /app/services/worker
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy HF_HOME=/opt/models/hf
COPY packages/score /app/packages/score
COPY services/worker/pyproject.toml services/worker/uv.lock ./
RUN uv sync --frozen --no-dev --extra ml --no-install-project
COPY services/worker/src ./src
RUN uv sync --frozen --no-dev --extra ml
# Bake the Demucs htdemucs_6s weights (safetensors) into the image, so the worker never
# downloads code-adjacent artefacts at run time (Basic Pitch's ONNX model ships in its wheel).
RUN uv run --no-sync python -c "from demucs.pretrained import get_model; get_model('htdemucs_6s')" \
 && chmod -R a+rX /opt/models
RUN useradd --system --uid 10001 worker
USER worker
ENV HF_HUB_OFFLINE=1 TABFORGE_WORKER_PIPELINE=real NUMBA_CACHE_DIR=/tmp
CMD ["uv", "run", "--no-sync", "python", "-m", "tabforge_worker"]

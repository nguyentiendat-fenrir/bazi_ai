FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c AS corpus
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.13.0
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --only-group corpus --no-install-project
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --uid 10001 --create-home app
COPY scripts/inspect_corpus.py scripts/inspect_corpus.py
USER app
CMD ["python", "scripts/inspect_corpus.py", "/inputs/books"]

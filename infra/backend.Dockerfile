FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.13.0 \
    && useradd --uid 10001 --create-home app

FROM base AS corpus
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --only-group corpus --no-install-project
ENV PATH="/app/.venv/bin:$PATH"
COPY scripts/inspect_corpus.py scripts/inspect_corpus.py
USER app
CMD ["python", "scripts/inspect_corpus.py", "/inputs/books"]

# API and workers share one image; the worker command differs (docs/03).
# Tesseract 5 from Debian bookworm with Vietnamese, English and Chinese data (T012);
# LibreOffice Writer (no GUI) and pinned font packages for canonical DOCX renders (T013).
FROM base AS app
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-vie \
       tesseract-ocr-eng tesseract-ocr-chi-sim tesseract-ocr-chi-tra \
       libreoffice-writer-nogui fonts-dejavu-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
# PostgreSQL 17 client for backup/restore (T052.1): pg_dump must not be older than the
# server, and Debian bookworm ships 15. The repository key is checked by fingerprint.
RUN apt-get update     && apt-get install -y --no-install-recommends ca-certificates curl gpg     && install -d /usr/share/postgresql-common/pgdg     && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc        https://www.postgresql.org/media/keys/ACCC4CF8.asc     && gpg --show-keys --with-colons /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc        | grep '^fpr' | grep -q 'B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8'     && echo 'deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc]'        'https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main'        > /etc/apt/sources.list.d/pgdg.list     && apt-get update     && apt-get install -y --no-install-recommends postgresql-client-17     && apt-get purge -y curl gpg && apt-get autoremove -y     && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH="/app/.venv/bin:$PATH" OMP_THREAD_LIMIT=1 STORAGE_ROOT=/data/objects
COPY backend backend
# Named volumes inherit this ownership on first mount, so the non-root user can write.
RUN mkdir -p /data/objects && chown app:app /data/objects
USER app
CMD ["celery", "-A", "backend.app.ingestion.celery_worker:celery", "worker", "-Q", "ingestion", "-c", "1"]

# Test image: app + dev/corpus groups + tests, for suites that need Tesseract/LibreOffice.
FROM app AS test
USER root
RUN uv sync --frozen --group dev --group corpus --no-install-project
COPY tests tests
COPY contracts contracts
COPY docs docs
USER app
CMD ["python", "-B", "-m", "unittest", "discover", "-s", "tests", "-v"]

FROM --platform=linux/amd64 python:3.11-slim@sha256:67e6a6053f28db54c173ad84a4bf88fdd4e338793dc09672e87ee38e3b1b378c

WORKDIR /app

ARG UV_VERSION=0.11.16
ARG UV_X86_64_SHA256=74947fe2c03315cf07e82ab3acc703eddef01aba4d5232a98e4c6825ec116131

# Install build-time and runtime system dependencies together.
# build-essential is needed only during pip install (compiling native extensions).
# libpq-dev provides the libpq shared library required by psycopg2 at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev

# Fetch the official x86-64 release artifact selected by the declared build
# platform, authenticate its bytes before extraction, and verify its version.
# No package installer or unverified binary participates in the trust root.
RUN python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz', '/tmp/uv.tar.gz')" && \
    echo "${UV_X86_64_SHA256}  /tmp/uv.tar.gz" | sha256sum --check - && \
    tar -xzf /tmp/uv.tar.gz -C /tmp && \
    install -m 0755 /tmp/uv-x86_64-unknown-linux-gnu/uv /usr/local/bin/uv && \
    install -m 0755 /tmp/uv-x86_64-unknown-linux-gnu/uvx /usr/local/bin/uvx && \
    test "$(uv --version)" = "uv ${UV_VERSION}" && \
    rm -rf /tmp/uv.tar.gz /tmp/uv-x86_64-unknown-linux-gnu

# Install the pipeline into its own locked environment. The API environment is
# kept separate because each project has an independently reviewed uv.lock.
COPY praviar_pipeline/pyproject.toml /app/praviar_pipeline/
COPY praviar_pipeline/uv.lock /app/praviar_pipeline/
COPY praviar_pipeline/src/ /app/praviar_pipeline/src/
COPY praviar_pipeline/data/abbreviations/ /app/praviar_pipeline/data/abbreviations/
WORKDIR /app/praviar_pipeline
RUN uv sync --locked --no-dev

# Install API dependencies from the API lock (production only — no dev extras).
COPY api/pyproject.toml /app/api/
COPY api/uv.lock /app/api/
COPY api/src/ /app/api/src/
WORKDIR /app/api
RUN uv sync --locked --no-dev

# Preserve API-lock precedence for shared dependencies, then append the locked
# pipeline environment for pipeline-only packages and the editable source tree.
RUN printf '%s\n' \
    '/app/praviar_pipeline/src' \
    '/app/praviar_pipeline/.venv/lib/python3.11/site-packages' \
    > /app/api/.venv/lib/python3.11/site-packages/praviar-pipeline-runtime.pth

ENV PATH="/app/api/.venv/bin:${PATH}"

# Purge build-only packages now that all pip installs are complete.
# libpq-dev is retained because psycopg2 links against the libpq shared library at runtime.
RUN apt-get purge -y build-essential && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Copy operational assets required at runtime
COPY api/alembic/ /app/api/alembic/
COPY api/alembic.ini /app/api/

EXPOSE 8080

# Health check — hit the shallow health endpoint every 30s
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health', timeout=4)"]

# Drop privileges: run as a non-root system user for defence in depth.
RUN adduser --system --uid 1001 --group appuser && chown -R appuser:appuser /app
USER appuser

# Single worker: uvicorn is async (asyncio event loop), so one worker fully
# utilises the CPU in a single container. Scale via container replicas instead.
# Migrations run through the Terraform-managed `api-migrate` Cloud Run Job.
# Cloud Run injects PORT=8080; we bind to the same port explicitly.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

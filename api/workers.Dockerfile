FROM --platform=linux/amd64 python:3.11-slim@sha256:67e6a6053f28db54c173ad84a4bf88fdd4e338793dc09672e87ee38e3b1b378c

WORKDIR /app

ARG UV_VERSION=0.11.16
ARG UV_X86_64_SHA256=74947fe2c03315cf07e82ab3acc703eddef01aba4d5232a98e4c6825ec116131
ARG TYPST_VERSION=0.14.2
ARG TYPST_X86_64_SHA256=a6044cbad2a954deb921167e257e120ac0a16b20339ec01121194ff9d394996d
ARG DECIMER_SEGMENTATION_MODEL_URL="https://zenodo.org/record/10663579/files/mask_rcnn_molecule.h5?download=1"
ARG DECIMER_SEGMENTATION_MODEL_SHA256=329120facb69e88add819a3216db0fbfef57e9a37d6b6db0f6149819a11d46a5
ARG PRAVIAR_BUILD_GIT_SHA
LABEL org.opencontainers.image.revision="${PRAVIAR_BUILD_GIT_SHA}"

# System deps: libpq for postgres, libgl1/libglib2.0 for OpenCV (DECIMER),
# build-essential for compiling native extensions.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libgl1 libglib2.0-0

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

# PDF exports are rendered inside the worker, not the API service. Install the
# official statically linked Typst release with an authenticated archive and
# fail the image build if the runtime version does not match the declared pin.
RUN python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/typst-x86_64-unknown-linux-musl.tar.xz', '/tmp/typst.tar.xz')" && \
    echo "${TYPST_X86_64_SHA256}  /tmp/typst.tar.xz" | sha256sum --check - && \
    python -c "import pathlib, tarfile; archive=tarfile.open('/tmp/typst.tar.xz', 'r:xz'); member=archive.getmember('typst-x86_64-unknown-linux-musl/typst'); pathlib.Path('/usr/local/bin/typst').write_bytes(archive.extractfile(member).read())" && \
    chmod 0755 /usr/local/bin/typst && \
    test "$(typst --version | awk '{print $2}')" = "${TYPST_VERSION}" && \
    rm -f /tmp/typst.tar.xz

# Keep the independently reviewed pipeline and API locks in separate
# environments, then expose both explicitly to the worker process.
COPY praviar_pipeline/pyproject.toml /app/praviar_pipeline/
COPY praviar_pipeline/uv.lock /app/praviar_pipeline/
COPY praviar_pipeline/src/ /app/praviar_pipeline/src/
COPY praviar_pipeline/data/abbreviations/ /app/praviar_pipeline/data/abbreviations/
WORKDIR /app/praviar_pipeline
RUN uv sync --locked --no-dev

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

# Derive the certification bundle from the exact runtime files baked into this
# image. The OCI digest is intentionally attached later by the isolated issuer
# because embedding an image's own digest would be circular.
RUN case "${PRAVIAR_BUILD_GIT_SHA}" in \
      *[!0-9a-f]*|'') exit 1 ;; \
    esac && \
    test "${#PRAVIAR_BUILD_GIT_SHA}" -eq 40 && \
    /app/praviar_pipeline/.venv/bin/python \
      -m praviar_pipeline.certification_subject \
      --git-sha "${PRAVIAR_BUILD_GIT_SHA}" \
      --output /opt/praviar-runtime-certification-bundle.json

ENV PATH="/app/api/.venv/bin:${PATH}"

# DECIMER and segmentation run in the isolated path expected by the pipeline.
# The complete transitive graph is exact and the committed lock artifact is
# SHA-256-bound before uv performs a strict, binary-only synchronization.
COPY api/requirements/decimer.lock /app/decimer-lock/decimer.lock
COPY api/requirements/decimer.lock.sha256 /app/decimer-lock/decimer.lock.sha256
RUN cd /app/decimer-lock && sha256sum --check decimer.lock.sha256 && \
    uv venv --python python3.11 --no-project --no-seed \
        /app/praviar_pipeline/venvs/decimer && \
    uv pip sync \
        --python /app/praviar_pipeline/venvs/decimer/bin/python \
        --strict \
        --require-hashes \
        --only-binary :all: \
        /app/decimer-lock/decimer.lock

# The upstream segmentation package otherwise downloads mutable weights on its
# first request. Resolve that network dependency at build time, authenticate the
# exact ML-BOM bytes, and install them read-only before dropping privileges.
RUN python -c "import urllib.request; urllib.request.urlretrieve('${DECIMER_SEGMENTATION_MODEL_URL}', '/tmp/mask_rcnn_molecule.h5')" && \
    echo "${DECIMER_SEGMENTATION_MODEL_SHA256}  /tmp/mask_rcnn_molecule.h5" | sha256sum --check - && \
    install -o root -g root -m 0444 \
        /tmp/mask_rcnn_molecule.h5 \
        /app/praviar_pipeline/venvs/decimer/lib/python3.11/site-packages/decimer_segmentation/mask_rcnn_molecule.h5 && \
    rm -f /tmp/mask_rcnn_molecule.h5

# Purge build-only packages.
RUN apt-get purge -y build-essential && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Copy operational assets required at runtime.
COPY api/alembic/ /app/api/alembic/
COPY api/alembic.ini /app/api/

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health', timeout=4)"]

RUN adduser --system --uid 1001 --group appuser && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

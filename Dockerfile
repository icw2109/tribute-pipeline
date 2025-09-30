## ---------------------------------------------------------------------------
## Tribute Pipeline Reproducible Container
## ---------------------------------------------------------------------------
## Goals:
##  * Deterministic base (pinned Python minor)
##  * Single COPY of sources after dependency layer for cache efficiency
##  * Optional install of full extras (zero‑shot / embeddings) via build arg
##  * Fast fail during build with selfcheck
##  * Simple runtime: `docker run image` launches an end‑to‑end Eigen demo
##  * Overridable seed & crawl parameters via environment variables
## ---------------------------------------------------------------------------

FROM python:3.12-slim AS runtime

ARG INSTALL_EXTRAS=1
ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1

# System build/runtime deps for lxml, ssl, and potential future extras
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev libxslt1-dev \
        ca-certificates \
        && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only dependency metadata first (improves cache reuse when source changes less frequently)
COPY pyproject.toml README.md ./

RUN pip install --upgrade pip && \
        if [ "$INSTALL_EXTRAS" = "1" ]; then pip install '.[full]' --no-cache-dir; else pip install . --no-cache-dir; fi

# Now copy source tree (kept after deps for layer caching)
COPY src ./src
COPY scripts ./scripts
COPY run_all.py ./run_all.py
COPY tag_vocabulary.json ./tag_vocabulary.json

# Run a lightweight selfcheck so build fails early if packaging breaks
RUN python - <<'PY'
import json,importlib
try:
        m=importlib.import_module('src.selfcheck')
        # selfcheck prints JSON already; just invoke
        m.main()
except Exception as e:
        raise SystemExit(f"Selfcheck failed during image build: {e}")
PY

# Runtime environment defaults (override with -e VAR=value)
ENV SEED_URL="https://blog.eigencloud.xyz" \
        MAX_PAGES=40 \
        MAX_DEPTH=2 \
        PER_PAGE_LINK_CAP=25 \
        ALL_FLAGS=1

# Minimal entrypoint allowing override; default subcommand `run` triggers pipeline
COPY <<'EOF' entrypoint.sh
#!/usr/bin/env bash
set -euo pipefail

cmd="$1" || true
if [ "$cmd" = "run" ] || [ "$cmd" = "" ]; then
    # Build base command
    if [ "${ALL_FLAGS}" = "1" ]; then
        exec tribute-e2e --url "${SEED_URL}" --maxPages "${MAX_PAGES}" --maxDepth "${MAX_DEPTH}" --perPageLinkCap "${PER_PAGE_LINK_CAP}" --all
    else
        exec tribute-run --url "${SEED_URL}" --maxPages "${MAX_PAGES}" --maxDepth "${MAX_DEPTH}" --perPageLinkCap "${PER_PAGE_LINK_CAP}" --auto-workdir
    fi
else
    shift || true
    exec "$cmd" "$@"
fi
EOF

RUN chmod +x entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["run"]

# Basic healthcheck: ensure console scripts still import (lightweight)
HEALTHCHECK --interval=45s --timeout=10s --start-period=25s --retries=3 \
    CMD tribute-selfcheck >/dev/null 2>&1 || exit 1

## Usage Examples:
## Build (full extras):  docker build -t tribute-pipeline:full --build-arg INSTALL_EXTRAS=1 .
## Build (core only):    docker build -t tribute-pipeline:core --build-arg INSTALL_EXTRAS=0 .
## Run default demo:     docker run --rm tribute-pipeline:full
## Custom seed:          docker run --rm -e SEED_URL=https://docs.python.org/3/ tribute-pipeline:full
## Inspect shell:        docker run -it --entrypoint /bin/bash tribute-pipeline:full
## Direct selfcheck:     docker run --rm tribute-pipeline:full tribute-selfcheck

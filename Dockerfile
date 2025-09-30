# Lightweight Python image
FROM python:3.12-slim

# System deps (if lxml needs build extras, add gcc/libxml2; keeping minimal first)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project metadata first for layer caching
COPY pyproject.toml README.md ./

# Install in editable mode (core deps). For full stack: use pip install .[full]
RUN pip install --upgrade pip && pip install -e .

# Copy source and scripts
COPY src ./src
COPY scripts ./scripts
COPY run_all.py ./run_all.py
COPY tag_vocabulary.json ./tag_vocabulary.json

# Default command shows help
CMD ["python", "scripts/run_pipeline.py", "--help"]

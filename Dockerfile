FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends procps \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY app/ ./app/

# Default dataset schema, baked in so the image runs standalone.
# Override at runtime with DATASET_SCHEMA (see README).
COPY schema.json ./app/schema.json

RUN pip install --no-cache-dir --no-deps .

# Non-root. Output files land in mounted volumes, so no write access to the
# image filesystem is needed. Remove these two lines if the host ./data
# directory is not writable by UID 1000.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
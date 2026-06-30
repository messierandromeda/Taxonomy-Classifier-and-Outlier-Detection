# Lightweight Python image.
FROM python:3.11-slim

# Prevent Python from buffering logs.
ENV PYTHONUNBUFFERED=1

# Prevent .pyc cache files.
ENV PYTHONDONTWRITEBYTECODE=1

# Working directory inside container.
WORKDIR /app

# System packages required for pandas/sklearn.
RUN apt-get update && apt-get install -y procps \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency file first for caching.
COPY requirements.txt .

# Install Python dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY . .

# Expose FastAPI port.
EXPOSE 8000

# Healthcheck for Docker.
HEALTHCHECK CMD curl --fail http://localhost:8000/health || exit 1

# Start FastAPI application.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
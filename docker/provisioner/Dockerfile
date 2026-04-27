FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    kubernetes

WORKDIR /app
COPY app.py .

EXPOSE 19833

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "19833"]

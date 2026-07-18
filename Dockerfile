FROM python:3.11-slim

WORKDIR /app

# System deps kept minimal; qdrant-client (embedded) and openai are pure-Python wheels.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

EXPOSE 8010

# Prefer a real Qdrant server in production: set QDRANT_URL and CATALOG_SOURCE=http.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]

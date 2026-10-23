# Multi-stage Dockerfile for DTU Academic Services Assistant
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies
COPY requirements.txt pyproject.toml ./

# Install python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code and data
COPY core/ ./core/
COPY graph/ ./graph/
COPY api/ ./api/
COPY ui/ ./ui/
COPY scripts/ ./scripts/
COPY eval/ ./eval/
COPY data/ ./data/
COPY main.py ./

# Pre-initialize SQLite, students, and document search indexes (Finding #6)
ENV PYTHONPATH=/app
ENV MOCK_LLM=true
RUN python -c "from core.database import init_db; init_db()" && \
    python scripts/load_students.py --dir data/test_students/ && \
    python -c "from core.chunking import chunk_all_documents; from core.retrieval import index_chunks; index_chunks(chunk_all_documents())"

EXPOSE 8000 8501

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

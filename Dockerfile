FROM python:3.12-slim

# Prevent Python from creating .pyc files and .pyo files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# First copy only requirements.txt to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create non-root user for security
RUN useradd -m -r -s /bin/false appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
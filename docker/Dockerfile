# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime deps early (optional)
COPY pyproject.toml README.md LICENSE /app/
COPY kvopt /app/kvopt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 9000

# Default command runs the API server
CMD ["python", "-m", "kvopt.server.main"]

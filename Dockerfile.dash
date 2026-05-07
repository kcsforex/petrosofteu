# syntax=docker/dockerfile:1.7-labs
FROM python:3.12.2-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements-dash.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements-dash.txt
COPY main.py .
COPY pages/ pages/
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD curl -fsS http://localhost:8000/health || exit 1
#CMD ["gunicorn", "main:server", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "--worker-tmp-dir", "/dev/shm", "0.0.0.0:8000"]
CMD ["gunicorn", "main:server", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "--preload", "-b", "0.0.0.0:8000"]
#CMD ["gunicorn", "main:server", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "--preload", "--worker-tmp-dir", "/dev/shm"," --timeout", "120", "-b", "0.0.0.0:8000"]

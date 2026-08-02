FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system crawler && useradd --system --gid crawler crawler
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN mkdir -p /data && chown -R crawler:crawler /data
USER crawler

EXPOSE 8090
ENV SIFTLANE_ENGINE_DATA_DIR=/data \
    SIFTLANE_ENGINE_BIND_ADDRESS=0.0.0.0

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health/ready', timeout=2)"]

CMD ["siftlane-engine"]

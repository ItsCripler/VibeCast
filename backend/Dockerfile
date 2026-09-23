FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv/vibecast

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system vibecast && useradd --system --gid vibecast --home-dir /srv/vibecast vibecast

WORKDIR /srv/vibecast
COPY backend/ ./
COPY scripts/ ./scripts/
ARG INSTALL_ESSENTIA=false
RUN if [ "$INSTALL_ESSENTIA" = "true" ]; then \
      pip install --no-cache-dir '.[analysis]'; \
    else \
      pip install --no-cache-dir .; \
    fi \
    && mkdir -p /data/uploads \
    && chown -R vibecast:vibecast /srv/vibecast /data/uploads

USER vibecast
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Backend image for Render / Railway / Fly.io / any container host.
# The dashboard is served by Netlify, so no frontend build happens here — the
# app skips its static mount when frontend/dist is absent.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Dependencies first so a code change does not reinstall them.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --upgrade pip && pip install -r backend/requirements.txt

COPY backend/ backend/

# The database lives on a mounted volume so scan results survive a redeploy.
# Without a volume the container keeps its own copy and loses it on restart.
ENV DATABASE_URL=sqlite:////data/cyber_opp.db
RUN mkdir -p /data

# Hosts inject the port to listen on; 8000 is the local default.
ENV PORT=8000
EXPOSE 8000

# Long-lived scans run inside the request worker, so the keep-alive has to
# outlast them and a single worker keeps the scan lock meaningful.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75"]

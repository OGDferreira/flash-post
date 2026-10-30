FROM node:22-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Pre-compressed copies: the server sends them as is instead of gzipping on every request.
RUN npm run build \
    && find dist -type f \( -name "*.js" -o -name "*.css" -o -name "*.svg" -o -name "*.html" -o -name "*.webmanifest" \) -size +1k -exec gzip -9 -k {} \;

FROM python:3.12-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend-builder /frontend/dist ./app/static

EXPOSE 10000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]

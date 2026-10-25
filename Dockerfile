# Multi-stage production build for REZOLV Sibiu
# Stage 1: Build Frontend Assets
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Minimal Python 3 Runtime (zero third-party dependencies)
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    REZOLV_HOST=0.0.0.0 \
    REZOLV_DATA_DIR=/app/backend/data \
    REZOLV_FRONTEND_DIST=/app/frontend/dist

# Create runtime directories
RUN mkdir -p /app/backend/data /app/backend/backups

# Copy backend source and compiled frontend
COPY backend/ /app/backend/
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Expose HTTP port (Render/Railway inject $PORT)
EXPOSE 8787

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request, os; port = os.environ.get('PORT', '8787'); urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health/live')" || exit 1

# Start the unified web server
CMD ["python3", "-m", "rezolv.server"]

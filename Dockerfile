# Multi-stage Docker build

# ── Stage 1: Python ETL ───────────────────────────────────────────────────────
FROM python:3.12-slim AS etl
WORKDIR /app/etl
COPY etl/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY etl/ .
COPY db/ /app/db/
# Copia i PDF (devono essere presenti nella directory)
# COPY pdfs/ /app/pdfs/
# RUN python build_db.py

# ── Stage 2: Backend ──────────────────────────────────────────────────────────
FROM node:20-alpine AS backend-build
WORKDIR /app/backend
COPY backend/package*.json .
RUN npm ci --only=production
COPY backend/tsconfig.json .
COPY backend/src ./src
RUN npm run build

# ── Stage 3: Frontend ─────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json .
RUN npm ci
COPY frontend/ .
ENV NEXT_PUBLIC_API_URL=http://localhost:3001
RUN npm run build

# ── Stage 4: Production ───────────────────────────────────────────────────────
FROM node:20-alpine AS production
WORKDIR /app

# Backend
COPY --from=backend-build /app/backend/dist ./backend/dist
COPY --from=backend-build /app/backend/node_modules ./backend/node_modules
COPY backend/package.json ./backend/

# Frontend
COPY --from=frontend-build /app/frontend/.next ./frontend/.next
COPY --from=frontend-build /app/frontend/node_modules ./frontend/node_modules
COPY --from=frontend-build /app/frontend/public ./frontend/public
COPY frontend/package.json ./frontend/
COPY frontend/next.config.js ./frontend/

# Database (deve essere copiato dopo ETL)
RUN mkdir -p db
COPY db/sciopero.db ./db/ 2>/dev/null || echo "DB da generare"

EXPOSE 3000 3001

# Script di avvio
RUN printf '#!/bin/sh\ncd /app/backend && node dist/server.js &\ncd /app/frontend && npm start\n' > /start.sh && chmod +x /start.sh

CMD ["/start.sh"]

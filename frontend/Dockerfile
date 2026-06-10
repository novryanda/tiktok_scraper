# ─────────────────────────────────────────────────────────────────────────────
# TikTok Scraper — Frontend Dockerfile (Next.js Standalone)
# Multi-stage build: deps → builder → runner
# Image final ~200MB (tanpa node_modules production)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Install dependencies ────────────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps


# ── Stage 2: Build Next.js ────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Pastikan folder public ada (Next.js standalone butuh ini)
RUN mkdir -p public

# Next.js rewrites() dievaluasi saat BUILD — BACKEND_URL harus tersedia di sini.
# Default: http://backend:8001 (nama service Docker Compose)
# Override: docker compose build --build-arg BACKEND_URL=http://myserver:8001
ARG BACKEND_URL=http://backend:8001
ENV BACKEND_URL=${BACKEND_URL}

RUN npm run build


# ── Stage 3: Production runner ────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Copy standalone server output (minimal deps)
COPY --from=builder /app/.next/standalone ./

# Copy static assets (JS/CSS/images yang dihasilkan Next.js)
COPY --from=builder /app/.next/static ./.next/static

# Copy public folder
COPY --from=builder /app/public ./public

EXPOSE 3000

# server.js adalah entry point standalone Next.js
CMD ["node", "server.js"]

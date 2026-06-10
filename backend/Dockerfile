# ─────────────────────────────────────────────────────────────────────────────
# TikTok Scraper — Backend Dockerfile
# Base : Python 3.11 slim
# Deps : FastAPI + Uvicorn + Playwright (Chrome for Testing)
# Note : SENTIMENT_MODE=rule_only → torch/transformers tidak diinstall
#        Ganti requirements.docker.txt ke requirements.txt untuk ML mode
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# ── System dependencies untuk Playwright/Chrome ───────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libxshmfence1 \
    libxss1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies (layer cache optimal) ─────────────────────────────
COPY requirements.docker.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.docker.txt

# ── Playwright: install Chromium + Chrome for Testing ────────────────────
# chromium  → dipakai cookie mode (tiktok_scraper.py, tanpa channel="chrome")
# chrome    → dipakai profile mode dan tiktok_profile_scraper.py (channel="chrome")
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install-deps chromium chrome \
    && playwright install chromium chrome

# ── Source code ───────────────────────────────────────────────────────────
COPY . .

# ── Direktori data (akan di-mount oleh volumes di production) ─────────────
RUN mkdir -p \
    engine/session \
    engine/output_tiktok \
    engine/output_tiktok_profiles \
    engine/tiktok_chrome_real_profile \
    tiktok_cookie_profile_persistent \
    tiktok_search_cookie_profile \
    _tmp_scripts \
    _tmp_search

# ── Environment defaults untuk Docker ────────────────────────────────────
# WAJIB: TIKTOK_HEADLESS=True karena tidak ada display di container
# Chrome akan otomatis pakai --no-sandbox jika berjalan sebagai root di container
ENV TIKTOK_HEADLESS=True \
    CHROME_NO_SANDBOX=True \
    TIKTOK_ENGINE_DIR=/app/engine \
    SENTIMENT_MODE=rule_only \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8001

# Jalankan sebagai root agar Chrome bisa berjalan tanpa sandbox di Docker
# (Docker sendiri sudah menyediakan isolasi di level container)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]

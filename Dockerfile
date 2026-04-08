# ════════════════════════════════════════════════════════════════════════════
# MELODIFY BOT - Docker Image (Optimized for Performance)
# Updated: April 5, 2026
# Base: Python 3.12-slim for minimal footprint
# ════════════════════════════════════════════════════════════════════════════

FROM python:3.12-slim

WORKDIR /app

# ─── INSTALL SYSTEM DEPENDENCIES ────────────────────────────────────────────
# FFmpeg: Audio processing and format conversion
# git: Version control (if needed during runtime)
# Playwright dependencies: Browser automation (chromium, firefox, webkit)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# ─── PYTHON DEPENDENCIES ────────────────────────────────────────────────────
# Copy and install requirements early for better layer caching
COPY requirements.txt .

# Install Python packages with optimizations
RUN pip install --no-cache-dir \
    --disable-pip-version-check \
    --prefer-binary \
    -r requirements.txt

# ─── PLAYWRIGHT SETUP ───────────────────────────────────────────────────────
# Install Playwright browsers and system dependencies
# This must be separate to avoid conflicts with FFmpeg/system deps
RUN pip install --no-cache-dir \
    --disable-pip-version-check \
    playwright && \
    playwright install --with-deps chromium && \
    playwright install-deps

# ─── APPLICATION CODE ──────────────────────────────────────────────────────
# Copy application files (after dependencies for better caching)
COPY . .

# ─── RUNTIME CONFIGURATION ────────────────────────────────────────────────
# Labels for metadata
LABEL maintainer="Melodify Bot"
LABEL description="Discord Music Bot with Multi-Platform Support"
LABEL version="2026.4.5"

# Python runtime optimization
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONOPTIMIZE=2 \
    PYTHONUTF8=1

# ─── ENTRYPOINT ────────────────────────────────────────────────────────────
CMD ["python", "playify.py"]

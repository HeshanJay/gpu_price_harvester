# --------------------------------------------------------------------
# Dockerfile  –  Cloud Functions (Gen 2) / Cloud Run ready
# --------------------------------------------------------------------
# • Uses an official Python 3.11 slim image.
# • Installs every shared library Chromium needs at runtime.
# • Installs Playwright + Chromium in the image layer
#   (kept under /root/.cache/ms-playwright, so the browser is present
#   on every cold start without downloading again).
# • No PLAYWRIGHT_BROWSERS_PATH override – avoids the /tmp problem.
# --------------------------------------------------------------------

FROM python:3.11-slim

# --------------------------------------------------
# 1. Linux packages required by Chromium
# --------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libx11-6 libx11-xcb1 libxcb1 libxext6 libxi6 \
    libxrender1 libxss1 libxtst6 ca-certificates fonts-liberation \
    xdg-utils && \
    rm -rf /var/lib/apt/lists/*

# --------------------------------------------------
# 2. App setup
# --------------------------------------------------
WORKDIR /app

# Requirements *first* for better layer-level caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --------------------------------------------------
# 3. Install Playwright + Chromium browser binaries
#    (stored in /root/.cache/ms-playwright)
# --------------------------------------------------
RUN python -m playwright install --with-deps chromium

# --------------------------------------------------
# 4. Add source code
# --------------------------------------------------
COPY . .

# --------------------------------------------------
# 5. Runtime env & start command
# --------------------------------------------------
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Functions Framework will look for the target
CMD ["functions-framework", "--target=process_all_gpu_prices_http", "--port=8080"]

FROM python:3.15-slim

# rebuild.sh removes old, unused images with this label only (never other images)
LABEL org.wegweiser.app="wegweiser"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/wegweiser.sqlite \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

WORKDIR /srv

COPY requirements.txt .
# Headless Chromium for server-side PDFs (app/services/pdf.py). Only the libraries the
# headless shell links against (instead of `playwright install --with-deps`, which also
# pulls in Xvfb and a dozen font packages). libgbm1 is linked but only used with a GPU:
# its Mesa/LLVM drivers (~200 MB) are removed again. Fonts: Latin, Cyrillic, Greek,
# Arabic, Tamil and Ethiopic come with the app (static/vendor); WenQuanYi covers Chinese
# and Japanese, DejaVu Hebrew and other scripts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 libatspi2.0-0t64 \
       libdbus-1-3 libdrm2 libgbm1 libglib2.0-0t64 libasound2t64 libxkbcommon0 \
       libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 \
       fontconfig fonts-wqy-zenhei fonts-dejavu-core \
    && dpkg --remove --force-depends mesa-libgallium libllvm19 libz3-4 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install chromium-headless-shell \
    && rm -rf /opt/ms-playwright/ffmpeg-* \
    && chmod -R a+rX /opt/ms-playwright

COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data && chown appuser:appuser /data

# Starts as root only to fix /data ownership, then runs the app as appuser.
EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

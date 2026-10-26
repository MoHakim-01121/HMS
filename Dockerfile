# ---- Builder stage: compile/Pillow/cffi wheels, discard toolchain afterward ----
FROM python:3.12-slim AS builder

# Build-time deps only — cffi/Pillow fall back to compiling here when no wheel
# is available. None of these -dev packages ship in the runtime image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libcairo2 \
    libcairo2-dev \
    libpango-1.0-0 \
    libpango1.0-dev \
    libffi-dev \
    libgobject-2.0-0 \
    python3-dev \
    pkg-config \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime stage: minimal, non-root, health-checked ----
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Jakarta \
    PORT=10000

# Runtime libs for WeasyPrint (cairo/pango) + file-type sniffing only.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libffi-dev \
    libgobject-2.0-0 \
    shared-mime-info \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin hms

WORKDIR /app
COPY --from=builder /install /usr/local
COPY . /app

RUN mkdir -p /app/logs /app/media /app/staticfiles \
    && chmod +x /app/bin/docker-entrypoint.sh \
    && chown -R hms:hms /app

USER hms

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:10000/health/', timeout=3)" || exit 1

# Run migrations + collectstatic (needs real SECRET_KEY, so at runtime, not
# build time) then start gunicorn as the non-root user.
ENTRYPOINT ["bin/docker-entrypoint.sh"]

# gthread workers tuned for the WeasyPrint PDF endpoints and the Inertia SPA;
# --preload matches bin/startup.sh so deployment config is identical here.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:10000", \
     "--worker-class", "gthread", \
     "--workers", "3", \
     "--threads", "4", \
     "--timeout", "120", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--access-logfile", "-", \
     "--log-file", "-"]
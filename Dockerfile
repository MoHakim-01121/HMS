FROM python:3.11-slim

# Install dependencies sistem yang tersedia di trixie
RUN apt-get update && apt-get install -y \
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
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

EXPOSE 10000

CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:10000", "--log-file", "-"]

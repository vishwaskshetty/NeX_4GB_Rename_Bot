FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        p7zip-full \
        aria2 \
        gcc \
        g++ \
        build-essential \
        python3-dev \
        procps && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir TgCrypto uvloop && \
    pip install --no-cache-dir -r requirements.txt && \
    python3 -c "import tgcrypto, uvloop; print('✅ VERIFIED C-EXTENSION BUILD:', tgcrypto.__file__)"

COPY . .

CMD ["python3", "bot.py"]

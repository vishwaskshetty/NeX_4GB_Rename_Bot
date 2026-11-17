FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        p7zip-full \
        aria2 \
        build-essential \
        python3-dev \
        procps && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel && \
    pip3 install --no-cache-dir tgcrypto uvloop && \
    pip3 install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3", "bot.py"]

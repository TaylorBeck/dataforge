FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY start.sh .
RUN chmod +x start.sh

RUN useradd -m -u 1000 dataforge && \
    chown -R dataforge:dataforge /app && \
    mkdir -p /tmp && \
    chown dataforge:dataforge /tmp
USER dataforge

EXPOSE 8000

CMD ["./start.sh"]
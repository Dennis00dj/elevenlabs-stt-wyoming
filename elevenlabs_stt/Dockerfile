FROM python:3.11-slim-bullseye

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Wyoming-Abhängigkeiten installieren
RUN pip3 install --no-cache-dir \
    wyoming \
    aiohttp \
    pydantic \
    requests

# Skripte kopieren
COPY elevenlabs_wyoming.py /app/
COPY config.json /app/
COPY run.sh /app/

RUN chmod +x /app/run.sh

ENTRYPOINT ["/app/run.sh"]
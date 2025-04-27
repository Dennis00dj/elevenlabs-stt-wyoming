#!/bin/bash

CONFIG_PATH=/data/options.json

# Prüfen, ob Konfigurationsdatei existiert
if [ ! -f "$CONFIG_PATH" ]; then
    echo "Fehler: Konfigurationsdatei nicht gefunden: $CONFIG_PATH"
    ls -la /data
    exit 1
fi

# API-Key aus der Konfiguration lesen
API_KEY=$(jq -r ".api_key // empty" $CONFIG_PATH)
PORT=$(jq -r ".port // \"10200\"" $CONFIG_PATH)
MODEL_ID=$(jq -r ".model_id // \"scribe_v1\"" $CONFIG_PATH)
DEBUG=$(jq -r ".debug // \"false\"" $CONFIG_PATH)

# Prüfen, ob API-Key vorhanden ist
if [ -z "$API_KEY" ]; then
    echo "Fehler: API-Key ist nicht konfiguriert"
    exit 1
fi

# Prüfen, ob Port eine Zahl ist
if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
    echo "Fehler: Port ist keine gültige Zahl, verwende Standard-Port 10200"
    PORT=10200
fi

# Debug-Flag überprüfen
DEBUG_FLAG=""
if [ "$DEBUG" = "true" ]; then
  DEBUG_FLAG="--debug"
fi

echo "Starte ElevenLabs Wyoming Service auf Port $PORT mit Model $MODEL_ID..."
python3 /app/elevenlabs_wyoming.py \
  --api-key "$API_KEY" \
  --port "$PORT" \
  --model-id "$MODEL_ID" \
  $DEBUG_FLAG
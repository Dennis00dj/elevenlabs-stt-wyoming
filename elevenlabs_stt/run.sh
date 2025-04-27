#!/bin/bash

CONFIG_PATH=/data/options.json

# API-Key aus der Konfiguration lesen
API_KEY=$(jq --raw-output ".api_key" $CONFIG_PATH)
PORT=$(jq --raw-output ".port" $CONFIG_PATH)
MODEL_ID=$(jq --raw-output ".model_id" $CONFIG_PATH)
DEBUG=$(jq --raw-output ".debug" $CONFIG_PATH)

# Debug-Flag überprüfen
DEBUG_FLAG=""
if [ "$DEBUG" = "true" ]; then
  DEBUG_FLAG="--debug"
fi

echo "Starte ElevenLabs Wyoming Service auf Port $PORT..."
python3 /app/elevenlabs_wyoming.py \
  --api-key "$API_KEY" \
  --port "$PORT" \
  --model-id "$MODEL_ID" \
  $DEBUG_FLAG

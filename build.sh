#!/bin/bash

# Skript zum Erstellen und Aktualisieren des Add-ons
set -e

# Arbeitsverzeichnis
ADDON_DIR="elevenlabs-stt-wyoming"

# Repository erstellen, falls nicht vorhanden
if [ ! -d "$ADDON_DIR" ]; then
  echo "Erstelle Repository-Struktur..."
  mkdir -p "$ADDON_DIR"
  cd "$ADDON_DIR"
  mkdir -p elevenlabs_stt
  
  # Initialisiere Git-Repository
  git init
  
  # README.md im Hauptverzeichnis
  cp ../README.md ./
  
  # Repository-Konfiguration
  cat > repository.json << EOL
{
  "name": "ElevenLabs Scribe STT Wyoming",
  "url": "https://github.com/yourusername/elevenlabs-stt-wyoming",
  "maintainer": "Ihr Name <your.email@example.com>"
}
EOL

else
  cd "$ADDON_DIR"
fi

# Add-on-Dateien kopieren
echo "Kopiere Add-on-Dateien..."
cp ../Dockerfile ./elevenlabs_stt/
cp ../elevenlabs_wyoming.py ./elevenlabs_stt/
cp ../config.json ./elevenlabs_stt/
cp ../run.sh ./elevenlabs_stt/

echo "Add-on erfolgreich erstellt!"
echo ""
echo "Um das Add-on zu Home Assistant hinzuzufügen:"
echo "1. Komprimieren Sie den Ordner '$ADDON_DIR' zu einer ZIP-Datei"
echo "2. Laden Sie die ZIP-Datei auf einen Webserver hoch oder erstellen Sie ein GitHub-Repository"
echo "3. Fügen Sie die URL als Repository in Home Assistant hinzu"
echo "   (Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories)"

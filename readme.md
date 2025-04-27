# ElevenLabs Scribe STT Add-on für Home Assistant
#readme.md

Dieses Add-on fügt ElevenLabs Scribe Speech-to-Text zu Home Assistant hinzu. Es verwendet das Wyoming-Protokoll, um nahtlos mit dem Voice Assistant zu integrieren.

## Überblick

ElevenLabs Scribe ist ein leistungsstarker Speech-to-Text-Dienst, der mehrere Sprachen unterstützt. Dieses Add-on macht ElevenLabs Scribe als STT-Provider in der Home Assistant Voice Assistant-UI auswählbar.

## Installation

1. Fügen Sie dieses Repository zu Ihren Add-on-Repositories hinzu:
   - Gehen Sie zu **Einstellungen** → **Add-ons** → **Add-on Store**
   - Klicken Sie auf das Menü in der oberen rechten Ecke und wählen Sie **Repositories**
   - Fügen Sie die folgende URL hinzu: `https://github.com/Dennis00dj/elevenlabs-stt-wyoming`
   - Klicken Sie auf **Hinzufügen**

2. Installieren Sie das Add-on:
   - Suchen Sie nach "ElevenLabs Scribe STT" in der Add-on-Liste
   - Falls nicht vorhanden einmal die Seite neuladen
   - Klicken Sie auf **Installieren**

3. Konfigurieren Sie das Add-on:
   - Geben Sie Ihren ElevenLabs API-Key ein
   - Konfigurieren Sie den Port (Standard: 10300)
   - Klicken Sie auf **Speichern**

4. Starten Sie das Add-on:
   - Klicken Sie auf **Start**
   
5. In Wyoming hinzufügen:
   - Öffne **Services und Dienste**
   - Integration hinzufügen
   - Im Voice-Assistant in speech to text auswählen

## Konfiguration

| Option | Beschreibung | Standard |
|--------|--------------|----------|
| `api_key` | Ihr ElevenLabs API-Key (erforderlich) | - |
| `port` | Der Port für den Wyoming-Server | 10300 |
| `model_id` | ElevenLabs Modell-ID | scribe_v1 |
| `debug` | Debug-Modus aktivieren | false |

## Verwendung mit dem Voice Assistant

1. Gehen Sie zu **Einstellungen** → **Voice Assistant**
2. Wählen Sie als STT-Engine "Wyoming"
3. Geben Sie folgende Einstellungen ein:
   - Host: `localhost` (oder Ihre Home Assistant IP)
   - Port: `10300` (oder der von Ihnen konfigurierte Port)
4. Speichern Sie die Einstellungen
5. Der Voice Assistant verwendet nun ElevenLabs Scribe für die Spracherkennung

## Unterstützte Sprachen

- Deutsch (de)
- Englisch (en)
- Spanisch (es)
- Französisch (fr)
- Italienisch (it)
- Japanisch (ja)
- Portugiesisch (pt)
- Niederländisch (nl)

## Fehlerbehebung

- Überprüfen Sie die Add-on-Logs, um mögliche Probleme zu identifizieren
- Stellen Sie sicher, dass Ihr API-Key gültig ist
- Prüfen Sie, ob der Port nicht von einer anderen Anwendung verwendet wird

## Lizenz

Dieses Projekt steht unter der MIT-Lizenz.

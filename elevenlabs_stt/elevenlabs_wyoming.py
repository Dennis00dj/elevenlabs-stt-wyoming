#!/usr/bin/env python3
"""Wyoming-Server für ElevenLabs STT."""
import argparse
import asyncio
import json
import logging
import os
import tempfile
import requests
import wave
from typing import Optional, List, Dict, Any

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStop
from wyoming.info import Describe, Info, Attribution, AsrModel, AsrProgram
from wyoming.server import AsyncServer

_LOGGER = logging.getLogger(__name__)

class ElevenLabsSTTServer(AsyncServer):
    """ElevenLabs STT-Server mit Wyoming-Protokoll."""

    def __init__(
        self,
        api_key: str,
        host: str,
        port: int,
        model_id: str = "scribe_v1",
    ):
        super().__init__(host, port)
        self.api_key = api_key
        self.model_id = model_id

    async def handle_client(self, client):
        """Handle client connection."""
        client_info = f"{client.writer.get_extra_info('peername')}"
        _LOGGER.info(f"Client verbunden: {client_info}")
        
        try:
            audio_buffer = bytes()
            language = "de"
            sample_rate = 16000
            sample_width = 2
            sample_channels = 1
            
            async for message in client:
                if isinstance(message, Describe):
                    models = [
                        AsrModel(
                            id="scribe_v1",
                            name="ElevenLabs Scribe",
                            languages=["de", "en", "es", "fr", "it", "ja", "pt", "nl"],
                        )
                    ]

                    attribution = Attribution(
                        name="ElevenLabs Scribe",
                        url="https://elevenlabs.io/speech-to-text",
                    )

                    await client.write_message(
                        Info(
                            asr=[
                                AsrProgram(
                                    name="elevenlabs_wyoming",
                                    attribution=attribution,
                                    models=models,
                                )
                            ]
                        )
                    )
                elif isinstance(message, Transcribe):
                    language = message.language or "de"
                    _LOGGER.debug(f"Transkription angefordert mit Sprache: {language}")
                elif isinstance(message, AudioChunk):
                    # Audio-Daten sammeln
                    audio_buffer += message.audio
                    sample_rate = message.rate
                    sample_width = message.width
                    sample_channels = message.channels
                elif isinstance(message, AudioStop):
                    # Audio-Streaming beendet, Verarbeitung starten
                    _LOGGER.debug(
                        f"Audio empfangen: {len(audio_buffer)} Bytes, {sample_rate} Hz, "
                        f"{sample_channels} Kanäle, {sample_width * 8} Bit"
                    )

                    if not audio_buffer:
                        _LOGGER.warning("Leerer Audio-Puffer erhalten")
                        await client.write_message(Transcript(text=""))
                        continue

                    # Audio-Daten in temporäre WAV-Datei schreiben
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                        temp_path = temp_file.name

                        # WAV-Datei schreiben
                        with wave.open(temp_path, "wb") as wav_file:
                            wav_file.setnchannels(sample_channels)
                            wav_file.setsampwidth(sample_width)
                            wav_file.setframerate(sample_rate)
                            wav_file.writeframes(audio_buffer)

                    # Audio-Puffer zurücksetzen
                    audio_buffer = bytes()

                    try:
                        # An ElevenLabs API senden
                        _LOGGER.debug(f"Sende Audio an ElevenLabs (Sprache: {language})")
                        text = await self._transcribe_audio(temp_path, language)
                        
                        # Ergebnis zurück an den Client senden
                        _LOGGER.debug(f"Sende Transkription zurück: {text}")
                        await client.write_message(Transcript(text=text))
                    except Exception as e:
                        _LOGGER.error(f"Fehler bei der Transkription: {e}")
                        await client.write_message(Transcript(text=""))
                    finally:
                        # Temporäre Datei löschen
                        os.unlink(temp_path)
        except Exception as e:
            _LOGGER.exception(f"Fehler beim Verarbeiten des Clients {client_info}: {e}")
        finally:
            _LOGGER.debug(f"Client-Verbindung geschlossen: {client_info}")

    async def _transcribe_audio(self, audio_path: str, language_code: str) -> str:
        """Transkribiere Audio mit ElevenLabs API."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._transcribe_audio_sync, audio_path, language_code
        )

    def _transcribe_audio_sync(self, audio_path: str, language_code: str) -> str:
        """Synchrone Transkription mit ElevenLabs API."""
        url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {"xi-api-key": self.api_key}
        
        with open(audio_path, "rb") as f:
            files = {"file": f}
            data = {"model_id": self.model_id, "language_code": language_code}
            
            _LOGGER.debug("Sende Audio an ElevenLabs API")
            response = requests.post(url, headers=headers, files=files, data=data)
            
        if response.status_code != 200:
            _LOGGER.error(
                f"ElevenLabs API-Fehler: {response.status_code} - {response.text}"
            )
            return ""
            
        result = response.json()
        text = result.get("text", "")
        _LOGGER.debug(f"Transkription: {text}")
        
        return text

async def main() -> None:
    """Hauptfunktion."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True, help="ElevenLabs API Key")
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=10200, help="Port (default: 10200)")
    parser.add_argument(
        "--model-id", default="scribe_v1", help="ElevenLabs Modell-ID (default: scribe_v1)"
    )
    parser.add_argument("--debug", action="store_true", help="Debug-Modus aktivieren")
    
    args = parser.parse_args()
    
    # Logging einrichten
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Server erstellen und starten
    server = ElevenLabsSTTServer(
        api_key=args.api_key,
        host=args.host,
        port=args.port,
        model_id=args.model_id,
    )
    
    try:
        _LOGGER.info(f"ElevenLabs Wyoming Server läuft auf {args.host}:{args.port}")
        await server.run()
    except KeyboardInterrupt:
        _LOGGER.info("Server-Shutdown durch Tastatur-Interrupt")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
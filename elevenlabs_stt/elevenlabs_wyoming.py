#!/usr/bin/env python3
"""Wyoming-Server für ElevenLabs STT."""
import argparse
import asyncio
import json
import logging
import os
import tempfile
import requests
from typing import Optional, List, Dict

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStop
from wyoming.client import AsyncClient
from wyoming.info import Describe, Info, Attribution, AsrModel, AsrProgram
from wyoming.server import AsyncServer

_LOGGER = logging.getLogger(__name__)

class ElevenLabsWyoming:
    """Wyoming-Server für ElevenLabs STT."""

    def __init__(
        self,
        api_key: str,
        host: str,
        port: int,
        model_id: str = "scribe_v1",
        sample_rate: int = 16000,
    ):
        self.api_key = api_key
        self.host = host
        self.port = port
        self.model_id = model_id
        self.sample_rate = sample_rate
        self.server: Optional[AsyncServer] = None
        self.clients: List[AsyncClient] = []

    async def start(self):
        """Startet den Wyoming-Server."""
        # Aktualisierte Methode zum Erstellen des Servers
        self.server = AsyncServer(self.host, self.port)
        _LOGGER.info("ElevenLabs Wyoming Server läuft auf %s:%s", self.host, self.port)

        await self.server.start()
        await self.server.handle_forever(self.handle_client)

    async def handle_client(self, client: AsyncClient):
        """Clientverbindungen verarbeiten."""
        self.clients.append(client)
        _LOGGER.debug("Client verbunden: %s", client)

        try:
            # Ausgangspuffer und Audio-Status
            audio_buffer = bytes()
            sample_rate = self.sample_rate
            sample_width = 2  # 16-bit
            sample_channels = 1  # mono

            async for message in client:
                if isinstance(message, Describe):
                    # Info über den Service liefern
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
                    # Transkription starten
                    language_code = message.language or "de"
                    _LOGGER.debug("Transkription mit Sprache: %s", language_code)
                elif isinstance(message, AudioChunk):
                    # Audio-Daten sammeln
                    audio_buffer += message.audio
                    sample_rate = message.rate
                    sample_width = message.width
                    sample_channels = message.channels
                elif isinstance(message, AudioStop):
                    # Audio-Streaming beendet, Verarbeitung starten
                    _LOGGER.debug(
                        "Audio empfangen: %s Bytes, %s Hz, %s Kanäle, %s Bit",
                        len(audio_buffer),
                        sample_rate,
                        sample_channels,
                        sample_width * 8,
                    )

                    if not audio_buffer:
                        _LOGGER.warning("Leerer Audio-Puffer erhalten")
                        await client.write_message(Transcript(text=""))
                        continue

                    # Audio-Daten in temporäre WAV-Datei schreiben
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                        temp_path = temp_file.name

                        # Python-Modul wave verwenden, um eine korrekte WAV-Datei zu schreiben
                        import wave
                        with wave.open(temp_path, "wb") as wav_file:
                            wav_file.setnchannels(sample_channels)
                            wav_file.setsampwidth(sample_width)
                            wav_file.setframerate(sample_rate)
                            wav_file.writeframes(audio_buffer)

                    # Audio-Puffer zurücksetzen
                    audio_buffer = bytes()

                    try:
                        # An ElevenLabs API senden
                        text = await self._transcribe_audio(temp_path, language_code)
                        
                        # Ergebnis zurück an den Client senden
                        await client.write_message(Transcript(text=text))
                    except Exception as e:
                        _LOGGER.error("Fehler bei der Transkription: %s", e)
                        await client.write_message(Transcript(text=""))
                    finally:
                        # Temporäre Datei löschen
                        os.unlink(temp_path)

        except Exception as e:
            _LOGGER.exception("Fehler beim Verarbeiten des Clients: %s", e)
        finally:
            # Client aus der Liste entfernen
            self.clients.remove(client)
            _LOGGER.debug("Client getrennt: %s", client)

    async def _transcribe_audio(self, audio_path: str, language_code: str) -> str:
        """Audio mit ElevenLabs API transkribieren."""
        # Synchronen API-Aufruf als Coroutine ausführen
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._transcribe_audio_sync, audio_path, language_code
        )

    def _transcribe_audio_sync(self, audio_path: str, language_code: str) -> str:
        """Audio synchron mit ElevenLabs API transkribieren."""
        url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {"xi-api-key": self.api_key}
        
        with open(audio_path, "rb") as f:
            files = {"file": f}
            data = {"model_id": self.model_id, "language_code": language_code}
            
            _LOGGER.debug("Sende Audio an ElevenLabs API")
            response = requests.post(url, headers=headers, files=files, data=data)
            
        if response.status_code != 200:
            _LOGGER.error(
                "ElevenLabs API-Fehler: %s - %s", 
                response.status_code, 
                response.text
            )
            return ""
            
        result = response.json()
        text = result.get("text", "")
        _LOGGER.debug("Transkription: %s", text)
        
        return text

    async def stop(self):
        """Server stoppen und Clients trennen."""
        if self.server:
            await self.server.stop()

        for client in self.clients:
            client.close()


async def main():
    """Hauptprogramm."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True, help="ElevenLabs API Key")
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=10300, help="Port (default: 10300)")
    parser.add_argument(
        "--model-id", default="scribe_v1", help="ElevenLabs Modell-ID (default: scribe_v1)"
    )
    parser.add_argument(
        "--sample-rate", 
        type=int, 
        default=16000, 
        help="Sample Rate (default: 16000)"
    )
    parser.add_argument("--debug", action="store_true", help="Debug-Modus aktivieren")
    
    args = parser.parse_args()
    
    # Logging einrichten
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Server erstellen und starten
    server = ElevenLabsWyoming(
        api_key=args.api_key,
        host=args.host,
        port=args.port,
        model_id=args.model_id,
        sample_rate=args.sample_rate,
    )
    
    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
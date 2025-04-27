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

import wyoming
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStop
from wyoming.info import Describe, Info, Attribution, AsrModel, AsrProgram

_LOGGER = logging.getLogger(__name__)

class ElevenLabsClient:
    """Client für ElevenLabs STT."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, service: 'ElevenLabsService'):
        self.reader = reader
        self.writer = writer
        self.service = service
        self.client_info = writer.get_extra_info("peername")
        self.audio_buffer = bytes()
        self.sample_rate = 16000
        self.sample_width = 2
        self.sample_channels = 1
        self.language = "de"

    async def handle(self) -> None:
        """Handle client connection."""
        _LOGGER.info(f"Client verbunden: {self.client_info}")
        
        try:
            # Wyoming message loop
            async for message_type, message_data in wyoming.async_read_messages(self.reader):
                if message_type == Describe.__qualname__:
                    await self._handle_describe()
                elif message_type == Transcribe.__qualname__:
                    transcribe = Transcribe.from_dict(message_data)
                    self.language = transcribe.language or "de"
                    _LOGGER.debug(f"Transkription angefordert mit Sprache: {self.language}")
                elif message_type == AudioChunk.__qualname__:
                    await self._handle_audio_chunk(AudioChunk.from_dict(message_data))
                elif message_type == AudioStop.__qualname__:
                    await self._handle_audio_stop()
                else:
                    _LOGGER.warning(f"Unbekannter Nachrichtentyp: {message_type}")
        except ConnectionError:
            _LOGGER.debug(f"Client getrennt: {self.client_info}")
        except Exception as e:
            _LOGGER.exception(f"Fehler beim Verarbeiten des Clients {self.client_info}: {e}")
        finally:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
            _LOGGER.debug(f"Client-Verbindung geschlossen: {self.client_info}")

    async def _handle_describe(self) -> None:
        """Beschreibung des Services senden."""
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

        info = Info(
            asr=[
                AsrProgram(
                    name="elevenlabs_wyoming",
                    attribution=attribution,
                    models=models,
                )
            ]
        )

        await wyoming.async_write_message(self.writer, info)

    async def _handle_audio_chunk(self, chunk: AudioChunk) -> None:
        """Audiodaten sammeln."""
        self.audio_buffer += chunk.audio
        self.sample_rate = chunk.rate
        self.sample_width = chunk.width
        self.sample_channels = chunk.channels

    async def _handle_audio_stop(self) -> None:
        """Audioverarbeitung abschließen und transkribieren."""
        if not self.audio_buffer:
            _LOGGER.warning("Leerer Audio-Puffer erhalten")
            await wyoming.async_write_message(self.writer, Transcript(text=""))
            return

        _LOGGER.debug(
            f"Audio empfangen: {len(self.audio_buffer)} Bytes, {self.sample_rate} Hz, "
            f"{self.sample_channels} Kanäle, {self.sample_width * 8} Bit"
        )

        # Audio-Daten in temporäre WAV-Datei schreiben
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
            temp_path = temp_file.name

            # WAV-Datei schreiben
            with wave.open(temp_path, "wb") as wav_file:
                wav_file.setnchannels(self.sample_channels)
                wav_file.setsampwidth(self.sample_width)
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(self.audio_buffer)

        # Audio-Puffer zurücksetzen
        self.audio_buffer = bytes()

        try:
            # An ElevenLabs API senden
            _LOGGER.debug(f"Sende Audio an ElevenLabs (Sprache: {self.language})")
            text = await self.service.transcribe_audio(temp_path, self.language)
            
            # Ergebnis zurück an den Client senden
            _LOGGER.debug(f"Sende Transkription zurück: {text}")
            await wyoming.async_write_message(self.writer, Transcript(text=text))
        except Exception as e:
            _LOGGER.error(f"Fehler bei der Transkription: {e}")
            await wyoming.async_write_message(self.writer, Transcript(text=""))
        finally:
            # Temporäre Datei löschen
            os.unlink(temp_path)

class ElevenLabsService:
    """ElevenLabs STT Wyoming Service."""

    def __init__(
        self,
        api_key: str,
        host: str,
        port: int,
        model_id: str = "scribe_v1",
    ):
        """Initialisiere den ElevenLabs STT Service."""
        self.api_key = api_key
        self.host = host
        self.port = port
        self.model_id = model_id
        self.server: Optional[asyncio.Server] = None

    async def start(self) -> None:
        """Starte den Server."""
        self.server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        
        _LOGGER.info(f"ElevenLabs Wyoming Server läuft auf {self.host}:{self.port}")
        
        async with self.server:
            await self.server.serve_forever()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Erstelle einen neuen Client und verarbeite ihn."""
        client = ElevenLabsClient(reader, writer, self)
        await client.handle()

    async def transcribe_audio(self, audio_path: str, language_code: str) -> str:
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
    service = ElevenLabsService(
        api_key=args.api_key,
        host=args.host,
        port=args.port,
        model_id=args.model_id,
    )
    
    try:
        await service.start()
    except KeyboardInterrupt:
        _LOGGER.info("Server-Shutdown durch Tastatur-Interrupt")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
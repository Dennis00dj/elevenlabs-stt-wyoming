#!/usr/bin/env python3
"""Wyoming-Server für ElevenLabs STT."""
import argparse
import asyncio
import logging
import os
import tempfile
import wave
import requests
from typing import Optional

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStop
from wyoming.event import Event
from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info
from wyoming.server import AsyncServer, AsyncEventHandler

# Try to import zeroconf, but continue if not available
try:
    from wyoming.zeroconf import register_server
    _HAVE_ZEROCONF = True
except ImportError:
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.warning("Zeroconf not available. Auto-discovery will not work.")
    _HAVE_ZEROCONF = False
    
    # Dummy function that does nothing
    async def register_server(name: str, port: int, host: Optional[str] = None) -> None:
        _LOGGER.warning("Skipping Zeroconf registration (module not available)")
        pass

_LOGGER = logging.getLogger(__name__)

# Version
VERSION = "1.1.3"  # Keep version same for now

class ElevenLabsEventHandler(AsyncEventHandler):
    """Event handler for Wyoming protocol clients."""

    def __init__(
        self,
        wyoming_info: Info,
        api_key: str,
        model_id: str,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.wyoming_info_event = wyoming_info.event()
        self.api_key = api_key
        self.model_id = model_id
        self._language = "de"  # Default language
        self._wav_dir = tempfile.TemporaryDirectory()
        self._wav_path = os.path.join(self._wav_dir.name, "speech.wav")
        self._wav_file: Optional[wave.Wave_write] = None

    async def handle_event(self, event: Event) -> bool:
        """Handle Wyoming protocol events."""
        if AudioChunk.is_type(event.type):
            chunk = AudioChunk.from_event(event)
            if self._wav_file is None:
                self._wav_file = wave.open(self._wav_path, "wb")
                self._wav_file.setframerate(chunk.rate)
                self._wav_file.setsampwidth(chunk.width)
                self._wav_file.setnchannels(chunk.channels)
            self._wav_file.writeframes(chunk.audio)
            return True

        if AudioStop.is_type(event.type):
            _LOGGER.debug(
                "Audio stopped. Transcribing with language=%s",
                self._language,
            )
            
            if self._wav_file is None:
                _LOGGER.warning("No audio received")
                await self.write_event(Transcript(text="").event())
                return False
                
            self._wav_file.close()
            self._wav_file = None
            
            try:
                # Transcribe using ElevenLabs API
                text = await self._transcribe_audio(self._wav_path, self._language)
                _LOGGER.info(text)
                await self.write_event(Transcript(text=text).event())
                _LOGGER.debug("Completed request")
            except Exception as e:
                _LOGGER.error(f"Error during transcription: {e}")
                await self.write_event(Transcript(text="").event())
            
            # Reset language to default
            self._language = "de"
            return False

        if Transcribe.is_type(event.type):
            transcribe = Transcribe.from_event(event)
            if transcribe.language:
                self._language = transcribe.language
                _LOGGER.debug("Language set to %s", transcribe.language)
            return True

        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            _LOGGER.debug("Sent info")
            return True

        return True

    async def _transcribe_audio(self, audio_path: str, language_code: str) -> str:
        """Transcribe audio with ElevenLabs API."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._transcribe_audio_sync, audio_path, language_code
        )

    def _transcribe_audio_sync(self, audio_path: str, language_code: str) -> str:
        """Synchronous transcription with ElevenLabs API."""
        url = "https://api.elevenlabs.io/v1/speech-to-text"
        headers = {"xi-api-key": self.api_key}
        
        with open(audio_path, "rb") as f:
            files = {"file": f}
            data = {"model_id": self.model_id, "language_code": language_code}
            
            _LOGGER.debug("Sending audio to ElevenLabs API")
            response = requests.post(url, headers=headers, files=files, data=data)
            
        if response.status_code != 200:
            _LOGGER.error(
                f"ElevenLabs API error: {response.status_code} - {response.text}"
            )
            return ""
            
        result = response.json()
        text = result.get("text", "")
        return text


async def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True, help="ElevenLabs API Key")
    parser.add_argument("--uri", required=True, help="unix:// or tcp:// URI")
    parser.add_argument(
        "--model-id", default="scribe_v1", help="ElevenLabs model ID (default: scribe_v1)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    _LOGGER.info(f"ElevenLabs Wyoming Server starting. Version: {VERSION}")
    
    # Supported languages
    supported_languages = ["de", "en", "es", "fr", "it", "ja", "pt", "nl"]
    
    # Create Wyoming info
    wyoming_info = Info(
        asr=[
            AsrProgram(
                name="elevenlabs_wyoming",
                description="ElevenLabs Scribe STT for Home Assistant",
                attribution=Attribution(
                    name="ElevenLabs",
                    url="https://elevenlabs.io/speech-to-text",
                ),
                installed=True,
                version=VERSION,
                models=[
                    AsrModel(
                        name="scribe_v1",
                        description="ElevenLabs Scribe",
                        attribution=Attribution(
                            name="ElevenLabs",
                            url="https://elevenlabs.io/speech-to-text",
                        ),
                        installed=True,
                        languages=supported_languages,
                        version=VERSION,
                    )
                ],
            )
        ],
    )
    
    # Parse URI to get host and port for zeroconf
    uri_parts = args.uri.split(":")
    if _HAVE_ZEROCONF and len(uri_parts) == 3 and uri_parts[0] == "tcp":
        # Format is tcp://host:port
        host = uri_parts[1].strip("/")
        if not host or host == "0.0.0.0":
            host = None  # Let zeroconf detect the IP
        
        port = int(uri_parts[2])
        
        # Register for zeroconf discovery
        await register_server("elevenlabs_wyoming", port, host)
    else:
        _LOGGER.warning("Skipping Zeroconf registration (not a TCP URI or zeroconf unavailable)")
    
    # Create server
    server = AsyncServer.from_uri(args.uri)
    
    # Store CLI args for use in the handler factory
    api_key = args.api_key
    model_id = args.model_id
    
    try:
        await server.run(
            lambda reader, writer: ElevenLabsEventHandler(
                wyoming_info, api_key, model_id, reader, writer
            )
        )
    except KeyboardInterrupt:
        _LOGGER.info("Server shutdown by keyboard interrupt")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
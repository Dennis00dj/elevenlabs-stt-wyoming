#!/usr/bin/env python3
"""Wyoming-Server für ElevenLabs STT."""
import argparse
import asyncio
import logging
import os
import tempfile
import uuid
import wave
import requests
from typing import Optional

from wyoming.server import AsyncServer
from wyoming.info import Info, Describe, AsrProgram, AsrModel, Attribution
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStop

_LOGGER = logging.getLogger(__name__)

class ElevenLabsSTTServer:
    """ElevenLabs STT Wyoming server."""

    def __init__(self, api_key: str, host: str, port: int, model_id: str = "scribe_v1"):
        """Initialize server."""
        self.api_key = api_key
        self.host = host
        self.port = port
        self.model_id = model_id

    async def start(self) -> None:
        """Run server."""
        server = AsyncServer.from_address(self.host, self.port)
        _LOGGER.info(f"ElevenLabs Wyoming Server starting on {self.host}:{self.port}")
        await server.run(self.handle_client)

    async def handle_client(self, connection) -> None:
        """Handle Wyoming client."""
        client_id = str(uuid.uuid4())
        _LOGGER.info(f"Client {client_id} connected")
        
        # Audio buffer and state
        audio_buffer = bytearray()
        language = "de"
        sample_rate = 16000
        sample_width = 2
        sample_channels = 1
        
        try:
            async for message in connection.messages():
                if isinstance(message, Describe):
                    # Respond with info
                    _LOGGER.debug("Received describe message")
                    
                    # Create response
                    info = Info(
                        asr=[
                            AsrProgram(
                                name="elevenlabs_wyoming",
                                attribution=Attribution(
                                    name="ElevenLabs Scribe",
                                    url="https://elevenlabs.io/speech-to-text",
                                ),
                                models=[
                                    AsrModel(
                                        id="scribe_v1",
                                        name="ElevenLabs Scribe",
                                        languages=["de", "en", "es", "fr", "it", "ja", "pt", "nl"],
                                    )
                                ],
                            )
                        ]
                    )
                    await connection.write_message(info)
                
                elif isinstance(message, Transcribe):
                    # Update language
                    language = message.language or "de"
                    _LOGGER.debug(f"Transcription requested with language: {language}")
                
                elif isinstance(message, AudioChunk):
                    # Collect audio data
                    audio_buffer.extend(message.audio)
                    sample_rate = message.rate
                    sample_width = message.width
                    sample_channels = message.channels
                
                elif isinstance(message, AudioStop):
                    # Process collected audio
                    if not audio_buffer:
                        _LOGGER.warning("Empty audio buffer")
                        await connection.write_message(Transcript(text=""))
                        continue
                    
                    _LOGGER.debug(
                        f"Audio received: {len(audio_buffer)} bytes, rate={sample_rate}, "
                        f"width={sample_width}, channels={sample_channels}"
                    )
                    
                    # Save audio to WAV file
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                        temp_path = temp_file.name
                        
                        with wave.open(temp_path, "wb") as wav_file:
                            wav_file.setnchannels(sample_channels)
                            wav_file.setsampwidth(sample_width)
                            wav_file.setframerate(sample_rate)
                            wav_file.writeframes(audio_buffer)
                    
                    # Reset audio buffer
                    audio_buffer = bytearray()
                    
                    try:
                        # Send to ElevenLabs API
                        _LOGGER.debug(f"Sending audio to ElevenLabs API (language: {language})")
                        text = await self._transcribe_audio(temp_path, language)
                        
                        # Send transcription back
                        _LOGGER.debug(f"Transcription: {text}")
                        await connection.write_message(Transcript(text=text))
                    except Exception as e:
                        _LOGGER.error(f"Error during transcription: {e}")
                        await connection.write_message(Transcript(text=""))
                    finally:
                        # Delete temporary file
                        try:
                            os.unlink(temp_path)
                        except Exception as e:
                            _LOGGER.error(f"Error deleting temporary file: {e}")
        
        except Exception as e:
            _LOGGER.exception(f"Error handling client {client_id}: {e}")
        finally:
            _LOGGER.info(f"Client {client_id} disconnected")

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
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=10200, help="Port (default: 10200)")
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
    
    # Create and start server
    server = ElevenLabsSTTServer(
        api_key=args.api_key,
        host=args.host,
        port=args.port,
        model_id=args.model_id,
    )
    
    try:
        await server.start()
    except KeyboardInterrupt:
        _LOGGER.info("Server shutdown by keyboard interrupt")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
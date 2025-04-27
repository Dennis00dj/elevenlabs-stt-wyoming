#!/usr/bin/env python3
"""Wyoming-Server für ElevenLabs STT."""
import argparse
import asyncio
import json
import logging
import os
import struct
import tempfile
import uuid
from enum import Enum
import wave
import requests
from typing import Dict, Any, Optional, AsyncGenerator, Tuple

_LOGGER = logging.getLogger(__name__)

# Wyoming-Protokoll-Grundlagen (direkte Implementierung)
MAGIC_BYTES = b"wyoming"

class WyomingMessage:
    """Wyoming message base class."""

    type: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON serializable dict."""
        raise NotImplementedError()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WyomingMessage":
        """Create from a dict."""
        return cls(**data)


class AsrModel:
    """ASR model info."""

    def __init__(self, id: str, name: str, languages: list[str]):
        self.id = id
        self.name = name
        self.languages = languages

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return {
            "id": self.id,
            "name": self.name,
            "languages": self.languages,
        }


class AsrProgram:
    """ASR program info."""

    def __init__(self, name: str, attribution=None, models=None):
        self.name = name
        self.attribution = attribution
        self.models = models or []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return {
            "name": self.name,
            "attribution": self.attribution.to_dict() if self.attribution else None,
            "models": [m.to_dict() for m in self.models] if self.models else [],
        }


class Attribution:
    """Attribution info."""

    def __init__(self, name: str, url: str = ""):
        self.name = name
        self.url = url

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return {"name": self.name, "url": self.url}


class Info(WyomingMessage):
    """Wyoming info message."""

    type = "info"

    def __init__(self, asr=None, **kwargs):
        self.asr = asr or []
        self.__dict__.update(kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return {
            "asr": [a.to_dict() for a in self.asr],
        }


class Describe(WyomingMessage):
    """Wyoming describe message."""

    type = "describe"

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to empty dict."""
        return {}


class Transcribe(WyomingMessage):
    """Wyoming transcribe message."""

    type = "transcribe"

    def __init__(self, language: Optional[str] = None, **kwargs):
        self.language = language
        self.__dict__.update(kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return {
            "language": self.language,
        }


class Transcript(WyomingMessage):
    """Wyoming transcript message."""

    type = "transcript"

    def __init__(self, text: str = "", **kwargs):
        self.text = text
        self.__dict__.update(kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return {"text": self.text}


class AudioChunk(WyomingMessage):
    """Wyoming audio chunk message."""

    type = "audio-chunk"

    def __init__(
        self,
        audio: bytes,
        rate: int = 16000,
        width: int = 2,
        channels: int = 1,
        **kwargs,
    ):
        self.audio = audio
        self.rate = rate
        self.width = width
        self.channels = channels
        self.__dict__.update(kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return {
            "rate": self.rate,
            "width": self.width,
            "channels": self.channels,
            "audio": self.audio,
        }


class AudioStop(WyomingMessage):
    """Wyoming audio stop message."""

    type = "audio-stop"

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to empty dict."""
        return {}


# Message types
MESSAGE_TYPES = {
    "describe": Describe,
    "info": Info,
    "transcribe": Transcribe,
    "transcript": Transcript,
    "audio-chunk": AudioChunk,
    "audio-stop": AudioStop,
}


async def read_message(reader: asyncio.StreamReader) -> Tuple[str, Dict[str, Any]]:
    """Read a Wyoming message from a stream."""
    # Header is:
    # 0-6: "wyoming"
    # 7: 1 (version)
    # 8-11: little-endian uint32 length of JSON bytes
    # 12-15: little-endian uint32 length of binary data bytes
    
    header = await reader.readexactly(16)
    
    if header[:7] != MAGIC_BYTES:
        raise ValueError(f"Invalid magic bytes: {header[:7]}")
    
    if header[7] != 1:
        raise ValueError(f"Invalid version: {header[7]}")
    
    json_len = struct.unpack("<I", header[8:12])[0]
    binary_len = struct.unpack("<I", header[12:16])[0]
    
    json_bytes = await reader.readexactly(json_len)
    json_str = json_bytes.decode("utf-8")
    
    message_dict = json.loads(json_str)
    message_type = message_dict.get("type", "")
    
    if not message_type:
        raise ValueError("Missing message type")
    
    message_data = message_dict.get("data", {})
    
    if binary_len > 0:
        binary_data = await reader.readexactly(binary_len)
        if message_type == "audio-chunk":
            message_data["audio"] = binary_data
    
    return message_type, message_data


async def write_message(writer: asyncio.StreamWriter, message: WyomingMessage) -> None:
    """Write a Wyoming message to a stream."""
    message_dict = {"type": message.type, "data": message.to_dict()}
    
    binary_data = b""
    if message.type == "audio-chunk":
        binary_data = message_dict["data"].pop("audio")
    
    json_str = json.dumps(message_dict)
    json_bytes = json_str.encode("utf-8")
    
    header = bytearray(16)
    header[:7] = MAGIC_BYTES
    header[7] = 1  # version
    header[8:12] = struct.pack("<I", len(json_bytes))
    header[12:16] = struct.pack("<I", len(binary_data))
    
    writer.write(header)
    writer.write(json_bytes)
    
    if binary_data:
        writer.write(binary_data)
    
    await writer.drain()


async def read_messages(reader: asyncio.StreamReader) -> AsyncGenerator[Tuple[str, Dict[str, Any]], None]:
    """Read Wyoming messages from a stream."""
    try:
        while True:
            message_type, message_data = await read_message(reader)
            yield message_type, message_data
    except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError) as e:
        _LOGGER.debug(f"Client disconnected: {e}")
    except Exception as e:
        _LOGGER.error(f"Error reading message: {e}")
        raise


class ElevenLabsSTTServer:
    """ElevenLabs STT Wyoming server."""

    def __init__(self, api_key: str, host: str, port: int, model_id: str = "scribe_v1"):
        """Initialize server."""
        self.api_key = api_key
        self.host = host
        self.port = port
        self.model_id = model_id
        self.server = None

    async def start(self) -> None:
        """Run server."""
        self.server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        async with self.server:
            await self.server.serve_forever()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle Wyoming client."""
        peername = writer.get_extra_info("peername")
        client_id = str(uuid.uuid4())
        _LOGGER.info(f"Client {client_id} connected from {peername}")
        
        # Audio buffer and state
        audio_buffer = bytes()
        language = "de"
        sample_rate = 16000
        sample_width = 2
        sample_channels = 1
        
        try:
            async for message_type, message_data in read_messages(reader):
                _LOGGER.debug(f"Received message: {message_type}")
                
                if message_type == "describe":
                    # Respond with info
                    _LOGGER.debug("Sending info")
                    
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
                    await write_message(writer, info)
                
                elif message_type == "transcribe":
                    # Update language
                    transcribe = Transcribe.from_dict(message_data)
                    language = transcribe.language or "de"
                    _LOGGER.debug(f"Transcription requested with language: {language}")
                
                elif message_type == "audio-chunk":
                    # Collect audio data
                    audio_chunk = AudioChunk.from_dict(message_data)
                    audio_buffer += audio_chunk.audio
                    sample_rate = audio_chunk.rate
                    sample_width = audio_chunk.width
                    sample_channels = audio_chunk.channels
                
                elif message_type == "audio-stop":
                    # Process collected audio
                    if not audio_buffer:
                        _LOGGER.warning("Empty audio buffer")
                        await write_message(writer, Transcript(text=""))
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
                    audio_buffer = bytes()
                    
                    try:
                        # Send to ElevenLabs API
                        _LOGGER.debug(f"Sending audio to ElevenLabs API (language: {language})")
                        text = await self._transcribe_audio(temp_path, language)
                        
                        # Send transcription back
                        _LOGGER.debug(f"Transcription: {text}")
                        await write_message(writer, Transcript(text=text))
                    except Exception as e:
                        _LOGGER.error(f"Error during transcription: {e}")
                        await write_message(writer, Transcript(text=""))
                    finally:
                        # Delete temporary file
                        os.unlink(temp_path)
        
        except Exception as e:
            _LOGGER.exception(f"Error handling client {client_id}: {e}")
        finally:
            writer.close()
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
    _LOGGER.info(f"ElevenLabs Wyoming Server starting on {args.host}:{args.port}")
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
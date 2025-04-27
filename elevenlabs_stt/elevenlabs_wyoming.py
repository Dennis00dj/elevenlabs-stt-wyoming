#!/usr/bin/env python3
"""Wyoming-Server für ElevenLabs STT."""
import argparse
import asyncio
import logging
import os
import tempfile
import wave
import requests
import json
import struct
from typing import Optional, Dict, Any

_LOGGER = logging.getLogger(__name__)

# Version information
VERSION = "1.1.3"


class WyomingEventHandler:
    """Handles Wyoming protocol events for a client connection."""

    def __init__(self, api_key: str, model_id: str):
        """Initialize the event handler."""
        self.api_key = api_key
        self.model_id = model_id
        self._language = "de"  # Default language
        self._wav_dir = tempfile.TemporaryDirectory()
        self._wav_path = os.path.join(self._wav_dir.name, "speech.wav")
        self._wav_file: Optional[wave.Wave_write] = None
        self._sample_rate = 16000
        self._sample_width = 2
        self._sample_channels = 1

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle a client connection."""
        client_id = os.urandom(8).hex()
        peername = writer.get_extra_info("peername")
        _LOGGER.info(f"Client {client_id} connected from {peername}")
        
        try:
            while True:
                # Read header (16 bytes)
                try:
                    header = await reader.readexactly(16)
                except asyncio.IncompleteReadError:
                    _LOGGER.debug(f"Client {client_id} disconnected")
                    break
                
                # Check magic bytes
                if header[0:7] != b"wyoming":
                    _LOGGER.error(f"Invalid magic bytes from {client_id}: {header[0:7]}")
                    break
                
                # Check protocol version
                if header[7] != 1:
                    _LOGGER.error(f"Unsupported protocol version from {client_id}: {header[7]}")
                    break
                
                # Get message size
                json_len = int.from_bytes(header[8:12], byteorder="little")
                payload_len = int.from_bytes(header[12:16], byteorder="little")
                
                # Read JSON data
                json_bytes = await reader.readexactly(json_len)
                json_data = json.loads(json_bytes)
                
                event_type = json_data.get("type")
                event_data = json_data.get("data", {})
                
                _LOGGER.debug(f"Received event: {event_type}")
                
                # Read payload if present
                payload = None
                if payload_len > 0:
                    payload = await reader.readexactly(payload_len)
                
                # Handle different event types
                if event_type == "describe":
                    # Send info response
                    info_data = {
                        "type": "info",
                        "data": {
                            "asr": [
                                {
                                    "name": "elevenlabs_wyoming",
                                    "description": "ElevenLabs Scribe STT for Home Assistant",
                                    "attribution": {
                                        "name": "ElevenLabs",
                                        "url": "https://elevenlabs.io/speech-to-text"
                                    },
                                    "installed": True,
                                    "version": VERSION,
                                    "models": [
                                        {
                                            "name": "scribe_v1",
                                            "description": "ElevenLabs Scribe",
                                            "attribution": {
                                                "name": "ElevenLabs",
                                                "url": "https://elevenlabs.io/speech-to-text"
                                            },
                                            "installed": True,
                                            "languages": ["de", "en", "es", "fr", "it", "ja", "pt", "nl"],
                                            "version": VERSION
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                    await self._send_message(writer, info_data)
                    _LOGGER.debug("Sent info response")
                
                elif event_type == "transcribe":
                    # Update language for transcription
                    if "language" in event_data and event_data["language"]:
                        self._language = event_data["language"]
                        _LOGGER.debug(f"Language set to {self._language}")
                
                elif event_type == "audio-chunk":
                    # Process audio chunk
                    if self._wav_file is None:
                        self._wav_file = wave.open(self._wav_path, "wb")
                        self._sample_rate = event_data.get("rate", 16000)
                        self._sample_width = event_data.get("width", 2)
                        self._sample_channels = event_data.get("channels", 1)
                        self._wav_file.setframerate(self._sample_rate)
                        self._wav_file.setsampwidth(self._sample_width)
                        self._wav_file.setnchannels(self._sample_channels)
                    
                    if payload:
                        self._wav_file.writeframes(payload)
                
                elif event_type == "audio-stop":
                    # Process complete audio for transcription
                    if self._wav_file is None:
                        _LOGGER.warning("No audio received")
                        transcript_data = {
                            "type": "transcript",
                            "data": {"text": ""}
                        }
                        await self._send_message(writer, transcript_data)
                        continue
                    
                    _LOGGER.debug(
                        f"Audio complete: rate={self._sample_rate}, "
                        f"width={self._sample_width}, channels={self._sample_channels}"
                    )
                    
                    self._wav_file.close()
                    self._wav_file = None
                    
                    try:
                        # Transcribe the audio
                        transcription_text = await self._transcribe_audio(self._wav_path, self._language)
                        _LOGGER.info(f"Transcription: {transcription_text}")
                        
                        # Send transcript response
                        transcript_data = {
                            "type": "transcript",
                            "data": {"text": transcription_text}
                        }
                        await self._send_message(writer, transcript_data)
                        
                    except Exception as e:
                        _LOGGER.error(f"Error during transcription: {e}")
                        transcript_data = {
                            "type": "transcript",
                            "data": {"text": ""}
                        }
                        await self._send_message(writer, transcript_data)
                    
                    # Reset language to default
                    self._language = "de"
                    
                else:
                    _LOGGER.warning(f"Unknown event type: {event_type}")
        
        except (ConnectionError, asyncio.CancelledError):
            _LOGGER.info(f"Client {client_id} disconnected")
        except Exception as e:
            _LOGGER.exception(f"Error handling client {client_id}: {e}")
        finally:
            # Clean up
            if self._wav_file is not None:
                self._wav_file.close()
                self._wav_file = None
            
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass
            _LOGGER.info(f"Client {client_id} disconnected")
    
    async def _send_message(self, writer: asyncio.StreamWriter, message: Dict[str, Any], payload: bytes = None) -> None:
        """Send a Wyoming protocol message."""
        # Convert message to JSON
        json_str = json.dumps(message)
        json_bytes = json_str.encode("utf-8")
        
        # Create header
        header = bytearray(16)
        header[0:7] = b"wyoming"  # Magic bytes
        header[7] = 1  # Protocol version
        header[8:12] = len(json_bytes).to_bytes(4, byteorder="little")  # JSON length
        
        # Add payload length if present
        payload_len = 0
        if payload is not None:
            payload_len = len(payload)
        header[12:16] = payload_len.to_bytes(4, byteorder="little")  # Payload length
        
        # Send header
        writer.write(header)
        
        # Send JSON
        writer.write(json_bytes)
        
        # Send payload if present
        if payload is not None and payload_len > 0:
            writer.write(payload)
        
        await writer.drain()
    
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
            
            _LOGGER.debug(f"Sending audio to ElevenLabs API with language {language_code}")
            response = requests.post(url, headers=headers, files=files, data=data)
            
        if response.status_code != 200:
            _LOGGER.error(
                f"ElevenLabs API error: {response.status_code} - {response.text}"
            )
            return ""
            
        result = response.json()
        text = result.get("text", "")
        return text


class WyomingServer:
    """Basic Wyoming protocol server implementation."""
    
    def __init__(self, host: str, port: int, handler_factory):
        """Initialize the server."""
        self.host = host
        self.port = port
        self.handler_factory = handler_factory
        self.server = None
    
    async def start(self):
        """Start the server."""
        self.server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        
        _LOGGER.info(f"Wyoming server started on {self.host}:{self.port}")
        
        async with self.server:
            await self.server.serve_forever()
    
    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a new client connection."""
        handler = self.handler_factory()
        await handler.handle_client(reader, writer)


async def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True, help="ElevenLabs API Key")
    parser.add_argument("--uri", required=True, help="Wyoming URI (tcp://host:port)")
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
    
    # Parse URI
    if not args.uri.startswith("tcp://"):
        _LOGGER.error("Only tcp:// URIs are supported")
        return
    
    host_port = args.uri[6:]  # Remove tcp://
    if ":" not in host_port:
        _LOGGER.error("URI must be in the format tcp://host:port")
        return
    
    host, port_str = host_port.split(":", 1)
    try:
        port = int(port_str)
    except ValueError:
        _LOGGER.error(f"Invalid port: {port_str}")
        return
    
    _LOGGER.info(f"Starting ElevenLabs STT Wyoming Server version {VERSION}")
    
    # Create handler factory
    def create_handler():
        return WyomingEventHandler(args.api_key, args.model_id)
    
    # Create and start server
    server = WyomingServer(host, port, create_handler)
    
    try:
        await server.start()
    except KeyboardInterrupt:
        _LOGGER.info("Server shutdown by keyboard interrupt")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
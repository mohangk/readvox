from __future__ import annotations

import asyncio
import logging
import math
import re
import time
import base64
import binascii
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from urllib.parse import urlencode

import websockets

from tts_app.providers.base import AudioChunk, ProviderError, TTSOptions
from tts_app.providers.options import (
    QWEN_CHINESE_VOICES,
    QWEN_ENGLISH_VOICES,
    SPEED_OPTIONS,
)

QwenConnect = Callable[..., Awaitable[object]]


class _ProtocolError(ProviderError):
    """Controlled diagnostic text, never an upstream free-form message."""


class QwenTTSProvider:
    name = "qwen"
    english_voices = QWEN_ENGLISH_VOICES
    chinese_voices = QWEN_CHINESE_VOICES
    speed_options = SPEED_OPTIONS

    def __init__(
        self,
        api_key: str | None,
        model: str,
        realtime_url: str,
        connect: QwenConnect | None = None,
        *, setup_timeout: float = 15, audio_timeout: float = 60,
        segment_timeout: float = 180, close_timeout: float = 5,
    ):
        self.api_key = api_key
        self.model = model
        self.realtime_url = realtime_url
        self.connect = connect or websockets.connect
        for value in (setup_timeout, audio_timeout, segment_timeout, close_timeout):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Qwen timeouts must be finite and positive")
        self.setup_timeout, self.audio_timeout = setup_timeout, audio_timeout
        self.segment_timeout, self.close_timeout = segment_timeout, close_timeout

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        if not self.api_key:
            raise ProviderError("API key is required for qwen provider")
        websocket = None
        primary_error = None
        phase = "connect"
        started = time.monotonic()
        session_id = request_id = None
        audio_received = False

        def identifier(value):
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value):
                return value
            return None

        async def receive(deadline):
            nonlocal session_id
            try:
                async with asyncio.timeout_at(deadline):
                    event = json.loads(await anext(events))
            except StopAsyncIteration as exc:
                raise _ProtocolError("qwen provider ended before a completed response") from exc
            if event.get("type") == "session.created":
                session_id = identifier((event.get("session") or {}).get("id"))
            if event.get("type") == "error":
                error = event.get("error") or {}
                code = identifier(error.get("code")) or "PROVIDER_ERROR"
                raise _ProtocolError(f"{code}: Qwen rejected the synthesis request")
            return event

        async def acknowledgement(expected):
            deadline = asyncio.get_running_loop().time() + self.setup_timeout
            while True:
                event = await receive(deadline)
                if event.get("type") == expected:
                    return
                if event.get("type") in {"session.finished", "response.done"}:
                    raise _ProtocolError("qwen provider ended during session setup")

        try:
            async with asyncio.timeout(self.segment_timeout):
                async with asyncio.timeout(self.setup_timeout):
                    websocket = await self.connect(self._build_url(options.model), additional_headers={"Authorization": f"Bearer {self.api_key}"})
                response = getattr(websocket, "response", None)
                if response is not None:
                    request_id = identifier(response.headers.get("x-request-id"))
                events = aiter(websocket)
                phase = "session creation"
                await acknowledgement("session.created")
                session = {
                    "voice": options.voice, "mode": "commit", "language_type": options.language,
                    "response_format": options.audio_format, "sample_rate": options.sample_rate,
                    "speech_rate": options.speed,
                }
                if options.instructions:
                    session["instructions"] = options.instructions
                phase = "session settings"
                await self._send_event(websocket, {"type": "session.update", "session": session})
                await acknowledgement("session.updated")
                phase = "text submission"
                await self._send_event(websocket, {"type": "input_text_buffer.append", "text": text})
                await self._send_event(websocket, {"type": "input_text_buffer.commit"})
                phase = "audio"
                deadline = asyncio.get_running_loop().time() + self.audio_timeout
                while True:
                    event = await receive(deadline)
                    event_type = event.get("type")
                    if event_type == "response.audio.delta":
                        data = self._decode_audio_delta(event)
                        audio_received = True
                        deadline = asyncio.get_running_loop().time() + self.audio_timeout
                        yield AudioChunk(data=data, mime_type=_mime_type(options.audio_format), extension=_extension(options.audio_format))
                    elif event_type == "response.done":
                        response = event.get("response")
                        status = response.get("status") if isinstance(response, dict) else None
                        if status != "completed":
                            raise _ProtocolError("qwen provider response did not complete successfully")
                        if not audio_received:
                            raise _ProtocolError("qwen provider returned no audio")
                        break
                    elif event_type == "session.finished":
                        raise _ProtocolError("qwen provider session finished before a completed response")
        except asyncio.CancelledError as exc:
            primary_error = exc
            raise
        except Exception as exc:
            if isinstance(exc, TimeoutError):
                reason = "Qwen request timed out"
            elif isinstance(exc, _ProtocolError):
                reason = str(exc)
            else:
                reason = f"Qwen transport or protocol failure ({type(exc).__name__})"
            context = f"phase={phase}, elapsed={time.monotonic() - started:.1f}s, audio_received={audio_received}"
            if session_id:
                context += f", session={session_id}"
            if request_id:
                context += f", request={request_id}"
            primary_error = ProviderError(f"qwen provider failed: {reason} ({context})")
            logging.getLogger(__name__).warning("qwen_synthesis_failed %s", primary_error)
            raise primary_error from None
        finally:
            if websocket is not None:
                try:
                    async with asyncio.timeout(self.close_timeout):
                        await websocket.close()
                except Exception as exc:
                    # Successful response.done is already a complete synthesis result.
                    if primary_error is None:
                        logging.getLogger(__name__).warning("qwen_close_failed type=%s", type(exc).__name__)

    def _build_url(self, model: str | None = None) -> str:
        separator = "&" if "?" in self.realtime_url else "?"
        return f"{self.realtime_url}{separator}{urlencode({'model': model or self.model})}"

    async def _send_event(self, websocket: object, event: dict) -> None:
        event["event_id"] = f"event_{uuid.uuid4().hex}"
        async with asyncio.timeout(self.setup_timeout):
            await websocket.send(json.dumps(event))

    def _decode_audio_delta(self, event: dict) -> bytes:
        delta = event.get("delta")
        if not isinstance(delta, str) or not delta:
            raise _ProtocolError("invalid audio delta from qwen provider")
        try:
            return base64.b64decode(delta, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise _ProtocolError("invalid audio delta from qwen provider") from exc


def _mime_type(audio_format: str) -> str:
    if audio_format == "mp3":
        return "audio/mpeg"
    if audio_format == "wav":
        return "audio/wav"
    if audio_format == "opus":
        return "audio/ogg"
    return "application/octet-stream"


def _extension(audio_format: str) -> str:
    if audio_format in {"mp3", "wav", "opus"}:
        return audio_format
    return "bin"

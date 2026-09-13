from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse
from tts_app.synthesis import (VoiceSampleRequest, InstructionVoiceSampleRequest, SAMPLE_TEXT, SAMPLE_LANGUAGES, _validate_language)

from tts_app.providers.base import TTSOptions
from tts_app.voice_catalog import public_voice, resolve_synthesis_voice
from tts_app.providers.options import SelectOption
from tts_app.voice_samples import VoiceSampleCache, VoiceSampleCacheError


logger = logging.getLogger(__name__)


def create_voice_sample_router(voice_sample_cache: VoiceSampleCache, storage, provider) -> APIRouter:
    router = APIRouter()

    @router.get("/voice-sample", response_class=HTMLResponse)
    async def voice_sample_page() -> str:
        return _static_file("index.html").read_text(encoding="utf-8")

    @router.get("/api/voice-sample/options")
    async def instruction_voice_sample_options():
        catalog = [public_voice(voice) for voice in storage.list_voices(provider.name)]
        default_voice = next((voice for voice in catalog if voice['available'] and 'en' in voice['languages']), None)
        return {
            "voice_catalog": catalog,
            "default_voice_id": default_voice['id'] if default_voice else None,
            "default_language": "en",
            "default_speed": 1.0,
            "languages": [{"value": key, "label": value} for key, value in SAMPLE_LANGUAGES.items()],
            "speeds": _option_dicts(provider.speed_options),
        }

    @router.post("/api/voice-sample")
    async def voice_sample(payload: VoiceSampleRequest):
        _validate_language(payload.language)
        text = SAMPLE_TEXT[payload.language]
        options = TTSOptions(
            voice=payload.voice,
            speed=payload.speed,
            language=SAMPLE_LANGUAGES[payload.language],
            audio_format="mp3",
        )
        try:
            audio, mime_type = await voice_sample_cache.get_or_create(
                text=text,
                options=options,
                language=payload.language,
            )
        except VoiceSampleCacheError as exc:
            logger.exception(
                "voice_sample_provider_failed model=%s voice=%s language=%s error=%s",
                voice_sample_cache.settings.qwen_model,
                payload.voice,
                payload.language,
                exc,
            )
            raise _provider_error() from exc
        return Response(content=audio, media_type=mime_type)

    @router.post("/api/voice-sample/instruction")
    async def instruction_voice_sample(payload: InstructionVoiceSampleRequest):
        selected=resolve_synthesis_voice(storage,provider,payload)
        options = TTSOptions(
            voice=selected['provider_voice_id'],
            model=selected['model'],
            speed=payload.speed,
            language=SAMPLE_LANGUAGES[payload.language],
            audio_format="mp3",
            instructions=payload.instructions,
        )
        try:
            audio, mime_type = await voice_sample_cache.get_or_create(
                text=payload.sample_text,
                options=options,
                language=payload.language,
                model=selected['model'],
            )
        except VoiceSampleCacheError as exc:
            logger.exception(
                "instruction_voice_sample_provider_failed model=%s voice=%s language=%s error=%s",
                selected['model'],
                selected['provider_voice_id'],
                payload.language,
                exc,
            )
            raise _provider_error() from exc
        return Response(content=audio, media_type=mime_type)

    @router.delete("/api/voice-samples/cache", status_code=204)
    async def clear_voice_sample_cache() -> Response:
        try:
            voice_sample_cache.clear()
        except VoiceSampleCacheError as exc:
            logger.exception("voice_sample_cache_clear_failed error=%s", exc)
            raise HTTPException(
                status_code=500,
                detail={"code": "cache_clear_failed", "message": "Unable to clear voice samples"},
            ) from exc
        return Response(status_code=204)

    return router


def _provider_error() -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "code": "provider_error",
            "message": "The speech provider could not generate this sample. Check the server logs for details.",
        },
    )


def _option_dicts(options: tuple[SelectOption, ...]) -> list[dict[str, str | float]]:
    return [{"value": option.value, "label": option.label} for option in options]


def _static_file(filename: str) -> Path:
    return Path(__file__).resolve().parents[1] / "static" / filename

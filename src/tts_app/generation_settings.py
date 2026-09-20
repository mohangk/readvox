"""Resolve request settings once; generation jobs consume only stored snapshots."""
from fastapi import HTTPException
from pydantic import BaseModel, Field
from tts_app.synthesis import SynthesisSettingsRequest, SAMPLE_LANGUAGES
from tts_app.voice_catalog import resolve_synthesis_voice


class GenerationSynthesisRequest(BaseModel):
    profile_id: int | None = Field(default=None, gt=0)
    voice: str | None = None
    voice_id: int | None = Field(default=None, gt=0)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = 'en'
    model: str | None = None
    instructions: str | None = None
    autoplay: bool = True


def resolve_generation_settings(payload, storage, settings, provider, required_language=None):
    if payload.profile_id is not None:
        if payload.model_fields_set & {'voice_id', 'voice', 'speed', 'language', 'model', 'instructions'}:
            raise HTTPException(400, 'A profile cannot be combined with explicit synthesis overrides')
        try:
            profile = storage.get_voice_profile(payload.profile_id)
        except KeyError:
            raise HTTPException(404, 'voice profile not found')
        selected=resolve_synthesis_voice(storage,provider,SynthesisSettingsRequest(
            **{key:profile[key] for key in ('voice_id','speed','language','instructions')}))
        if required_language is not None and profile['language'] != required_language:
            raise HTTPException(400, 'Select a voice profile matching the OCR draft language')
        return {**{key: profile[key] for key in ('speed', 'language', 'instructions')},
                'model':selected['model'], 'voice':selected['provider_voice_id'],
                'profile_id': profile['id'], 'profile_name': profile['name'], 'voice_id':selected['id'],
                'voice_name':selected['name'], 'provider':selected['provider'], 'autoplay': payload.autoplay}
    if payload.voice_id is not None:
        raise HTTPException(400, 'Generate with a saved profile_id when selecting a catalog voice')
    if payload.language not in SAMPLE_LANGUAGES:
        raise HTTPException(400, 'language must be en or zh')
    return {'voice': payload.voice or (settings.default_chinese_voice if payload.language == 'zh' else settings.default_english_voice),
            'speed': payload.speed, 'language': payload.language, 'model': settings.qwen_model,
            'instructions': '', 'autoplay': payload.autoplay}

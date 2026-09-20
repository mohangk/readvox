from sqlite3 import IntegrityError

from fastapi import APIRouter, HTTPException, Response
from pydantic import Field, field_validator

from tts_app.synthesis import SynthesisSettingsRequest, MAX_INSTRUCTION_SAMPLE_CHARS
from tts_app.voice_catalog import resolve_synthesis_voice, public_voice


class VoiceProfileRequest(SynthesisSettingsRequest):
    name: str = Field(min_length=1, max_length=120)
    preview_text: str = Field(min_length=1, max_length=MAX_INSTRUCTION_SAMPLE_CHARS)

    @field_validator('name', 'preview_text')
    @classmethod
    def nonempty(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('must not be empty')
        return value


def create_voice_profile_router(storage, provider):
    router = APIRouter(prefix='/api/voice-profiles')

    @router.get('')
    async def list_profiles():
        return storage.list_voice_profiles()

    @router.get('/{profile_id}')
    async def get_profile(profile_id: int):
        try:
            return storage.get_voice_profile(profile_id)
        except KeyError:
            raise HTTPException(404, 'voice profile not found')

    def save(payload, profile_id=None):
        voice=resolve_synthesis_voice(storage,provider,payload)
        try:
            return storage.save_voice_profile({**payload.model_dump(exclude={'model', 'voice'}),'voice_id':voice['id']}, profile_id)
        except IntegrityError:
            raise HTTPException(409, 'A voice profile with this name already exists')
        except KeyError:
            raise HTTPException(404, 'voice profile not found')

    @router.post('', status_code=201)
    async def create_profile(payload: VoiceProfileRequest):
        return save(payload)

    @router.put('/{profile_id}')
    async def update_profile(profile_id: int, payload: VoiceProfileRequest):
        return save(payload, profile_id)

    @router.delete('/{profile_id}', status_code=204)
    async def delete_profile(profile_id: int):
        try:
            storage.delete_voice_profile(profile_id)
        except KeyError:
            raise HTTPException(404, 'voice profile not found')
        return Response(status_code=204)

    return router


def create_voice_catalog_router(storage):
    router=APIRouter(prefix='/api/voices')

    @router.get('')
    async def list_voices():
        return [public_voice(voice) for voice in storage.list_voices()]

    return router

"""Resolve one catalog voice for profile validation, preview and generation."""
from fastapi import HTTPException

from tts_app.synthesis import _validate_language


def public_voice(voice):
    return {key: voice[key] for key in (
        'id', 'key', 'provider', 'provider_voice_id', 'name', 'kind', 'available',
        'model', 'languages', 'supports_instructions')}


def resolve_catalog_voice(storage, provider, *, voice_id=None, voice=None):
    if voice_id is not None:
        try:
            selected=storage.get_voice(voice_id)
        except KeyError:
            raise HTTPException(400,{'code':'unknown_voice','message':'Select an available voice'})
        if voice is not None and voice != selected['provider_voice_id']:
            raise HTTPException(400,'voice_id conflicts with the explicit provider voice')
    else:
        selected=next((candidate for candidate in storage.list_voices(provider.name)
                       if candidate['provider_voice_id']==voice),None)
        if selected is None:
            raise HTTPException(400,{'code':'unsupported_voice','message':'Select an available voice'})
    if selected['provider']!=provider.name:
        raise HTTPException(400,{'code':'provider_unavailable','message':'This voice requires a different configured speech provider'})
    if not selected['available']:
        raise HTTPException(400,{'code':'voice_unavailable','message':'This voice is currently unavailable; choose another voice'})
    return selected


def resolve_synthesis_voice(storage, provider, payload):
    selected = resolve_catalog_voice(storage, provider, voice_id=payload.voice_id, voice=payload.voice)
    if payload.model is not None and payload.model != selected['model']:
        raise HTTPException(400, {'code': 'unsupported_model',
                                  'message': 'The explicit model conflicts with this voice’s catalog model'})
    _validate_language(payload.language)
    if payload.language not in selected['languages']:
        raise HTTPException(400, {'code': 'unsupported_voice_language',
                                  'message': 'This voice does not support the selected language'})
    if payload.instructions and not selected['supports_instructions']:
        raise HTTPException(400, {'code': 'unsupported_instructions',
                                  'message': 'This voice does not support instructions'})
    return selected

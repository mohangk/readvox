from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from tts_app.synthesis import SynthesisSettingsRequest
from tts_app.voice_catalog import resolve_synthesis_voice
from tts_app.storage import Storage


def test_catalog_declares_language_without_provider_specific_capabilities(tmp_path):
    storage = Storage(tmp_path/'app.db'); storage.init_schema()
    voice = storage.install_voices([dict(key='reader', provider='custom', provider_voice_id='reader',
        name='Reader', kind='builtin', available=True, model='custom-model', languages=['en'],
        supports_instructions=True, metadata={})])[0]
    payload = SynthesisSettingsRequest(voice_id=voice['id'], language='zh', instructions='')
    with pytest.raises(HTTPException) as error:
        resolve_synthesis_voice(storage, SimpleNamespace(name='custom'), payload)
    assert error.value.status_code == 400
    assert error.value.detail['code'] == 'unsupported_voice_language'

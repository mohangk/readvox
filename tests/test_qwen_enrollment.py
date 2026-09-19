import json
import wave

import httpx
import pytest

from tts_app.providers.base import ProviderError
from tts_app.providers.qwen_enrollment import CLONE_MODEL, QwenEnrollment, preferred_name


def reference(tmp_path):
    path = tmp_path / 'reference.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\0\0' * 72000)
    return path


@pytest.mark.asyncio
async def test_create_audio_only_and_lookup(tmp_path):
    requests = []
    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if body['input']['action'] == 'list':
            return httpx.Response(200, json={'output': {'voice_list': [{'voice': 'qwen-tts-vc-example', 'target_model': CLONE_MODEL}]}})
        return httpx.Response(200, json={'output': {'voice': 'qwen-tts-vc-example', 'target_model': CLONE_MODEL, 'fallback_mode': False}, 'request_id': 'req'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = QwenEnrollment('secret', 'https://dashscope-intl.aliyuncs.com/api/v1/services/audio/tts/customization', client=client)
        result = await adapter.create(reference(tmp_path), 'kai123')
        assert result['voice'] == 'qwen-tts-vc-example'
        assert result['fallback_mode'] is False
        assert result['endpoint_region'] == 'dashscope-intl.aliyuncs.com'
        assert result['account_fingerprint'] != 'secret'
        assert (await adapter.lookup())['voice_list'][0]['voice'] == result['voice']
    assert set(requests[0]['input']) == {'action', 'target_model', 'preferred_name', 'language', 'audio'}
    assert requests[0]['input']['audio']['data'].startswith('data:audio/wav;base64,')


@pytest.mark.asyncio
@pytest.mark.parametrize('output', [{'voice': 'qwen-tts-vc-x', 'target_model': 'wrong'}, {}])
async def test_model_mismatch_rejected(tmp_path, output):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'output': output}))) as client:
        with pytest.raises(ProviderError, match='voice|model'):
            await QwenEnrollment('key', 'https://dashscope-intl.aliyuncs.com/api/v1/services/audio/tts/customization', client=client).create(reference(tmp_path), 'kai123')


def test_preferred_names_are_readable_unique_and_short():
    a, b = preferred_name('readvox-kai-v2'), preferred_name('readvox-kai-v2')
    assert a != b
    assert a.startswith('readvoxkai')
    assert len(a) <= 16 and a.isalnum()

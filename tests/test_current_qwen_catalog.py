"""Exercise current catalog bindings through each real generation route."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from tts_app.api import create_app
from tts_app.extractor import ExtractedText
from tts_app.providers.fake import FakeTTSProvider
from tts_app.voice_catalog_sync import sync_voice_catalog


@pytest.mark.parametrize('source', ['text', 'url', 'image'])
def test_current_chinese_profile_generates_without_obsolete_model_or_instructions(unpopulated_settings, monkeypatch, source):
    settings = replace(unpopulated_settings, provider_name='qwen')
    sync_voice_catalog(settings)
    class LocalQwen(FakeTTSProvider):
        name = 'qwen'
    monkeypatch.setattr('tts_app.api.get_provider', lambda _: LocalQwen())
    async def extract(url):
        return ExtractedText(title='Chinese URL', text='中文内容。', url=url)
    monkeypatch.setattr('tts_app.api.fetch_and_extract', extract)
    app = create_app(settings, run_background_inline=True)
    with TestClient(app) as client:
        profile = next(p for p in client.get('/api/voice-profiles').json() if p['language'] == 'zh')
        kai = next(v for v in client.get('/api/voices').json() if v['provider_voice_id'] == 'Kai')
        profile.update(voice_id=kai['id'], voice='Kai', speed=1.25)
        assert profile['instructions'] == ''
        assert client.put(f"/api/voice-profiles/{profile['id']}", json=profile).status_code == 200
        payload = {'profile_id': profile['id']}
        if source == 'image':
            draft = app.state.storage.create_ocr_draft(ocr_model='fake', language='zh', status='completed')
            app.state.storage.update_ocr_draft(draft, language='zh', combined_text='中文内容。', image_texts={})
            route = f'/api/ocr-drafts/{draft}/generation'
        else:
            route = f'/api/generations/{source}'
            payload.update({'text': '中文内容。'} if source == 'text' else {'url': 'https://example.test'})
        response = client.post(route, json=payload)
        assert response.status_code == 200
        detail = app.state.storage.get_generation(response.json()['generation_id'])
        assert detail['generation']['status'] == 'completed'
        snapshot = detail['generation']['settings']
        assert snapshot['model'] == 'qwen3-tts-flash-realtime'
        assert snapshot['instructions'] == '' and snapshot['language'] == 'zh' and snapshot['speed'] == 1.25
        assert snapshot['voice'] == 'Kai'
        path = settings.data_dir / detail['audio_segments'][0]['file_path']
        assert b'model=qwen3-tts-flash-realtime' in path.read_bytes()

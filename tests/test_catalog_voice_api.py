from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from tts_app.api import create_app
from tts_app.storage import Storage



@pytest.fixture
def installed(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    definition = dict(key='readvox-kai-v1', provider='fake',
                      model='qwen3-tts-vc-realtime-2026-01-15', voice='test-enrolled-kai',
                      language='en', name='Kai Narrator', speed=1.1, instructions='',
                      preview_text='A calm voice for reading.', reference_path='voices/test/reference.wav',
                      reference_sha256='a' * 64, provenance={'selection': 16})
    reference = test_settings.data_dir / definition['reference_path']
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b'reference recording')
    from tts_app.voice_installation import installation_voice
    voice=storage.install_voices([installation_voice(definition)])[0]
    return storage.save_voice_profile({**definition,'voice_id':voice['id']})


def test_catalog_is_read_only_and_every_profile_is_editable(test_settings, installed):
    with TestClient(create_app(test_settings)) as client:
        profile=client.get(f"/api/voice-profiles/{installed['id']}").json()
        assert 'system_key' not in profile and 'is_system' not in profile
        catalog=client.get('/api/voices').json()
        clone=next(v for v in catalog if v['id']==profile['voice_id'])
        assert clone['kind']=='cloned' and clone['name']=='Kai Narrator'
        assert 'metadata' not in clone and 'reference_path' not in clone
        assert client.post('/api/voices',json=clone).status_code==405
        assert client.delete(f"/api/voices/{clone['id']}").status_code in (404,405)
        options=client.get('/api/voice-sample/options').json()
        assert options['voice_catalog']==[v for v in catalog if v['provider']=='fake']
        assert clone['supports_instructions'] is False and clone['languages'] == ['en']
        assert 'model' not in profile
        payload={key:profile[key] for key in ('voice_id','name','language','speed','instructions','preview_text')}
        saved=client.put(f"/api/voice-profiles/{profile['id']}",json={**payload,'speed':1.25})
        assert saved.status_code==200 and saved.json()['speed']==1.25
        created=client.post('/api/voice-profiles',json={**payload,'name':'My Kai'})
        assert created.status_code==201 and created.json()['voice_id']==clone['id']
        assert client.delete(f"/api/voice-profiles/{profile['id']}").status_code==204
        assert client.delete(f"/api/voice-profiles/{created.json()['id']}").status_code==204
    with TestClient(create_app(test_settings)) as client:
        assert client.get(f"/api/voice-profiles/{installed['id']}").status_code==404
        assert any(v['id']==clone['id'] for v in client.get('/api/voices').json())


def test_unsaved_preview_and_validation_cache_retains_reference(test_settings, installed):
    app = create_app(test_settings)
    with TestClient(app) as client:
        payload = {key: installed[key] for key in ('voice_id','language','speed','instructions')}
        payload.update(sample_text='Preview unsaved changes.', speed=1.25)
        response = client.post('/api/voice-sample/instruction', json=payload)
        assert response.status_code == 200, response.text
        assert b'speed=1.25' in response.content and installed['voice'].encode() in response.content
        assert client.get('/api/generations').json() == []
        assert app.state.storage.get_voice_profile(installed['id'])['speed'] == 1.1
        for field, value in [('voice', 'not-enrolled'), ('model', 'qwen3-tts-instruct-flash-realtime'),
                             ('language', 'zh'), ('instructions', 'Unsupported')]:
            rejected = client.post('/api/voice-sample/instruction', json={**payload, field: value})
            assert rejected.status_code == 400, rejected.text
        second = client.post('/api/voice-sample/instruction', json={**payload, 'speed': 1.0})
        assert second.content != response.content
        assert client.delete('/api/voice-samples/cache').status_code == 204
        assert (test_settings.data_dir / 'voices/test/reference.wav').read_bytes() == b'reference recording'
        assert app.state.storage.list_voices('fake')


@pytest.mark.parametrize('mode', ['text', 'url', 'ocr'])
def test_all_generation_paths_use_clone_snapshot(test_settings, installed, monkeypatch, mode):
    from tts_app.extractor import ExtractedText
    text = 'A passage for the registered voice. ' * 10
    async def extract(url):
        return ExtractedText(url=url, title='Source', text=text)
    monkeypatch.setattr('tts_app.api.fetch_and_extract', extract)
    app = create_app(test_settings, run_background_inline=True)
    with TestClient(app) as client:
        if mode == 'ocr':
            draft = app.state.storage.create_ocr_draft(ocr_model='fake', language='en', status='completed')
            app.state.storage.update_ocr_draft(draft, language='en', combined_text=text, image_texts={})
            path, payload = f'/api/ocr-drafts/{draft}/generation', {}
        else:
            path = f'/api/generations/{mode}'
            payload = {'text': text} if mode == 'text' else {'url': 'https://example.com/article'}
        response = client.post(path, json={**payload, 'profile_id': installed['id']})
        assert response.status_code == 200, response.text
        detail = app.state.storage.get_generation(response.json()['generation_id'])
        settings = detail['generation']['settings']
        assert detail['generation']['status'] == 'completed'
        assert {key: settings[key] for key in ('model','voice','speed','language','instructions')} == {
            **{key: installed[key] for key in ('voice','speed','language','instructions')},
            'model': app.state.storage.get_voice(installed['voice_id'])['model']}
        assert settings['profile_name'] == settings['voice_name'] == 'Kai Narrator'
        assert settings['voice_id']==installed['voice_id'] and settings['provider']=='fake'
        assert len(detail['audio_segments']) > 1
        for audio in (test_settings.audio_dir / str(detail['generation']['id'])).glob('*.mp3'):
            data = audio.read_bytes()
            assert b'speed=1.1' in data and b'voice=test-enrolled-kai' in data
            assert b'model=qwen3-tts-vc-realtime-2026-01-15' in data
            assert b'instructions=\n' in data


def test_clone_cannot_change_chinese_ocr_draft(test_settings, installed):
    app = create_app(test_settings)
    draft = app.state.storage.create_ocr_draft(ocr_model='fake', language='zh', status='completed')
    app.state.storage.update_ocr_draft(draft, language='zh', combined_text='中文', image_texts={})
    before = deepcopy(app.state.storage.get_ocr_draft(draft))
    with TestClient(app) as client:
        response = client.post(f'/api/ocr-drafts/{draft}/generation', json={'profile_id': installed['id'], 'combined_text': 'Wrong'})
        assert response.status_code == 400
    assert app.state.storage.get_ocr_draft(draft) == before


async def test_editing_personal_clone_during_job_keeps_all_segment_settings(test_settings, installed):
    from tts_app.generation_settings import GenerationSynthesisRequest, resolve_generation_settings
    from tts_app.providers.base import AudioChunk
    app = create_app(test_settings)
    storage, service = app.state.storage, app.state.service
    profile = storage.save_voice_profile({**installed, 'name': 'Personal clone'})
    snapshot = resolve_generation_settings(GenerationSynthesisRequest(profile_id=profile['id']), storage, test_settings, service.provider)
    generation = await service.create_from_text('Independent sentences preserve the selected voice. ' * 10,
                                                 title='Clone snapshot', voice=profile['voice'], settings=snapshot)
    calls = []
    class MutatingProvider:
        name = 'fake'
        async def stream_speech(self, text, options):
            calls.append(options)
            if len(calls) == 1:
                storage.save_voice_profile({**profile, 'speed': 1.5}, profile['id'])
                storage.delete_voice_profile(profile['id'])
                with storage.connection() as conn:
                    conn.execute('UPDATE voices SET model=? WHERE id=?', ('future-catalog-model', profile['voice_id']))
            yield AudioChunk(data=b'FAKE-TTS audio', mime_type='audio/mpeg', extension='mp3')
    service.provider = MutatingProvider()
    await service.run_generation(generation)
    assert len(calls) > 1
    assert all(option.voice == snapshot['voice'] and option.model == snapshot['model'] and option.speed == 1.1
               and option.instructions == '' and option.language == 'English' for option in calls)
    assert storage.get_generation(generation)['generation']['settings'] == snapshot


def test_missing_reference_does_not_remove_usable_registration(test_settings, installed, caplog):
    (test_settings.data_dir / 'voices/test/reference.wav').unlink()
    with TestClient(create_app(test_settings)) as client:
        assert client.get(f"/api/voice-profiles/{installed['id']}").status_code == 200
    assert 'voice_reference_missing' in caplog.text


@pytest.mark.parametrize('body', [None, 1, ['system_key'], 'system_key'])
def test_profile_non_object_requests_return_validation_error(test_settings, body):
    with TestClient(create_app(test_settings)) as client:
        assert client.post('/api/voice-profiles', json=body).status_code == 422


def test_catalog_ids_validate_identity_availability_and_provider(test_settings, installed):
    app=create_app(test_settings,run_background_inline=True)
    with TestClient(app) as client:
        payload={key:installed[key] for key in ('voice_id','language','speed','instructions')}
        assert client.post('/api/voice-sample/instruction',json={**payload,'sample_text':'Preview','voice':'conflicting'}).status_code==400
        assert client.post('/api/voice-profiles',json={**payload,'voice_id':9999,'name':'Missing','preview_text':'Preview'}).status_code==400
        with app.state.storage.connection() as conn:
            conn.execute('UPDATE voices SET provider=? WHERE id=?',('other',installed['voice_id']))
        assert client.post('/api/generations/text',json={'profile_id':installed['id'],'text':'Wrong provider'}).status_code==400
        with app.state.storage.connection() as conn:
            conn.execute('UPDATE voices SET provider=?,available=0 WHERE id=?',('fake',installed['voice_id']))
        assert client.post('/api/generations/text',json={'profile_id':installed['id'],'text':'Unavailable'}).status_code==400
        assert client.get('/api/generations').json()==[]


def test_non_qwen_adapter_uses_same_catalog_profile_and_generation_path(test_settings, monkeypatch):
    from dataclasses import replace
    from tts_app.providers.fake import FakeTTSProvider
    class AnotherProvider(FakeTTSProvider):
        name='another-provider'
    storage=Storage(test_settings.db_path)
    storage.install_voices([dict(key='another-reader',provider='another-provider',provider_voice_id='reader',
        name='Reader',kind='builtin',available=True,model='reading-model',languages=['en'],supports_instructions=False,metadata={})])
    monkeypatch.setattr('tts_app.api.get_provider',lambda settings:AnotherProvider())
    app=create_app(replace(test_settings,provider_name='another-provider'),run_background_inline=True)
    with TestClient(app) as client:
        voice=next(v for v in client.get('/api/voices').json() if v['provider']=='another-provider')
        assert voice['provider']=='another-provider' and voice['name']=='Reader'
        defaults=client.get('/api/voice-profiles').json()
        assert len(defaults)==1 and defaults[0]['instructions']==''
        response=client.post('/api/generations/text',json={'text':'Provider-independent catalog.','profile_id':defaults[0]['id']})
        assert response.status_code==200,response.text
        detail=app.state.storage.get_generation(response.json()['generation_id'])
        assert detail['generation']['status']=='completed'
        assert detail['generation']['provider']=='another-provider'
        assert detail['generation']['settings']['voice_name']=='Reader'
        assert detail['generation']['settings']['model']=='reading-model'

"""The public editor contract selects a voice, never a synthesis model."""
from dataclasses import replace

from fastapi.testclient import TestClient

from tts_app.api import create_app


def test_profile_preview_and_generation_resolve_catalog_model(test_settings):
    app = create_app(test_settings, run_background_inline=True)
    with TestClient(app) as client:
        voice = next(v for v in client.get('/api/voices').json() if v['available'])
        payload = dict(name='Voice-owned model', voice_id=voice['id'], language='en', speed=1.25,
                       instructions='', preview_text='A preview using catalog settings.')
        response = client.post('/api/voice-profiles', json=payload)
        assert response.status_code == 201, response.text
        profile = response.json()
        assert 'model' not in profile
        preview = client.post('/api/voice-sample/instruction', json={
            **{k: payload[k] for k in ('voice_id', 'language', 'speed', 'instructions')},
            'sample_text': payload['preview_text']})
        assert preview.status_code == 200, preview.text
        assert f"model={voice['model']}".encode() in preview.content
        response = client.post('/api/generations/text', json={'profile_id': profile['id'], 'text': 'A saved reading profile.'})
        snapshot = app.state.storage.get_generation(response.json()['generation_id'])['generation']['settings']
        assert snapshot['model'] == voice['model']
        assert snapshot['voice_id'] == voice['id'] and snapshot['speed'] == 1.25


def test_options_are_flat_and_reload_catalog_without_restart(test_settings):
    app = create_app(test_settings)
    with TestClient(app) as client:
        options = client.get('/api/voice-sample/options').json()
        assert not {'models', 'voices_by_model', 'model_capabilities', 'default_model'} & options.keys()
        voice = options['voice_catalog'][0]
        assert 'models' not in voice and isinstance(voice['languages'], list)
        with app.state.storage.connection() as conn:
            conn.execute('UPDATE voices SET model=? WHERE id=?', ('replacement-model', voice['id']))
        refreshed = client.get('/api/voice-sample/options').json()['voice_catalog'][0]
        assert refreshed['model'] == 'replacement-model'


def test_empty_catalog_can_start_without_seeding_invalid_defaults(test_settings, tmp_path):
    root = tmp_path / 'empty'
    settings = replace(test_settings, data_dir=root, db_path=root/'app.db', audio_dir=root/'audio', image_dir=root/'images')
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/voices').json() == []
        assert client.get('/api/voice-profiles').json() == []
        options = client.get('/api/voice-sample/options').json()
        assert options['voice_catalog'] == [] and options['default_voice_id'] is None


def test_first_profile_after_empty_start_does_not_conflict_with_default_seeding(unpopulated_settings):
    from tts_app.providers.qwen_catalog import qwen_voice_definitions
    from tts_app.voice_storage import builtin_voice_key
    settings = unpopulated_settings
    app = create_app(settings)
    app.state.storage.sync_provider_voices('fake', [{**v, 'provider':'fake',
        'key':builtin_voice_key('fake',v['provider_voice_id'])} for v in qwen_voice_definitions()])
    with TestClient(app) as client:
        voice = client.get('/api/voices').json()[0]
        response = client.post('/api/voice-profiles', json=dict(name='English audiobook', voice_id=voice['id'],
            language='en', speed=1.25, instructions='', preview_text='My first profile.'))
        assert response.status_code == 201
        profile = response.json()
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/voice-profiles/{profile['id']}").json() == profile

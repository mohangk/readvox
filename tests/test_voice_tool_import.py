import copy
import json
import wave

import pytest

from tts_app.voice_tools.legacy_import import import_legacy_comparison
from tts_app.voice_tools.manifest import load_manifest, resolve_asset


@pytest.fixture
def legacy(tmp_path):
    run_id = '20260913T043114Z-0f3d936a'
    run = tmp_path / 'legacy' / run_id
    run.mkdir(parents=True)
    settings = {'voice': 'Elias', 'model': 'qwen3-tts-instruct-flash-realtime', 'speed': 1.25, 'instructions': 'Narrate calmly', 'language': 'English', 'sample_rate': 24000, 'audio_format': 'pcm', 'pitch': 1.0, 'volume': 1.0}
    data = {'run_id': run_id, 'gallery_run_id': 'gallery', 'clone_model': 'qwen3-tts-vc-realtime-2026-01-15', 'settings': settings, 'reference_text': 'Reference passage', 'passages': [{'text': 'Evaluation', 'source_segment_indexes': [1]}], 'voices': []}
    for number, voice, speed in [(16, 'Kai', 1.0), (11, 'Vivian', 1.1), (6, 'Bellona', 1.25), (1, 'Neil', 1.0)]:
        filename = f'{number}-reference.wav'
        with wave.open(str(run / filename), 'wb') as audio:
            audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            audio.writeframes(b'\0\0' * 72000)
        record = {'number': number, 'voice': voice, 'speed': speed, 'status': 'completed', 'preferred_name': f'rv{number}', 'reference_audio': run_id + '/' + filename,
                  'enrollment': {'voice': 'qwen-tts-vc-' + voice, 'target_model': data['clone_model'], 'request_id': f'req{number}', 'fallback_reason': 'reported'}, 'tracks': {}}
        for mode in ['original', 'cloned']:
            trackfile = f'{number}-{mode}.wav'
            (run / trackfile).write_bytes((run / filename).read_bytes())
            record['tracks'][mode] = {'status': 'completed', 'audio': run_id + '/' + trackfile, 'boundaries': [0.0], 'duration': 3.0,
                                     'segments': [{'audio': run_id + '/' + trackfile, 'duration': 3.0}], 'model': data['clone_model'] if mode == 'cloned' else settings['model'], 'speed': speed, 'instructions': '' if mode == 'cloned' else settings['instructions']}
        data['voices'].append(record)
    path = run / 'manifest.json'
    path.write_text(json.dumps(data))
    return path


def test_import_preserves_bytes_per_voice_settings_and_fallback(legacy, tmp_path, monkeypatch):
    import hashlib
    from tts_app.voice_tools import approved
    original = json.loads(legacy.read_text())
    monkeypatch.setattr(approved, 'APPROVED_MANIFEST_SHA256', hashlib.sha256(legacy.read_bytes()).hexdigest())
    monkeypatch.setattr(approved, 'APPROVED_REFERENCE_SHA256', {v['number']: hashlib.sha256((legacy.parent.parent / v['reference_audio']).read_bytes()).hexdigest() for v in original['voices']})
    before = legacy.read_bytes()
    output = tmp_path / 'converted'
    assert import_legacy_comparison(legacy, output, check=True) == output / 'manifest.json'
    assert not output.exists()
    path = import_legacy_comparison(legacy, output)
    imported = load_manifest(path)
    assert [v['key'] for v in imported['voices']] == ['readvox-kai-v1', 'readvox-vivian-v1', 'readvox-bellona-v1', 'readvox-neil-v1']
    for voice, expected_speed in zip(imported['voices'], [1.0, 1.1, 1.25, 1.0]):
        assert voice['speed'] == expected_speed
        assert voice['reference']['provenance']['settings']['speed'] == expected_speed
        assert voice['reference']['provenance']['settings']['voice'] == voice['name'].split()[0]
        assert voice['enrollment']['fallback_reason'] == 'reported'
        assert voice['comparisons'][1]['boundaries'] == [0.0]
        assert resolve_asset(path, voice['reference']['path']).read_bytes() == (legacy.parent / f'{voice["reference"]["provenance"]["sample_number"]}-reference.wav').read_bytes()
        assert voice['acceptance']['source'] == 'historical-selection'
    assert legacy.read_bytes() == before
    with pytest.raises(ValueError, match='new'):
        import_legacy_comparison(legacy, output)


def test_import_rejects_path_escape_before_writing(legacy, tmp_path):
    data = json.loads(legacy.read_text())
    data['voices'][0]['reference_audio'] = '../outside.wav'
    legacy.write_text(json.dumps(data))
    output = tmp_path / 'bad'
    with pytest.raises(ValueError, match='escape|root|run'):
        import_legacy_comparison(legacy, output)
    assert not output.exists()


def test_unapproved_speed_does_not_inherit_historical_acceptance(legacy, tmp_path):
    data = json.loads(legacy.read_text())
    data['voices'][0]['speed'] = 1.5
    data['voices'][0]['tracks']['cloned']['speed'] = 1.5
    legacy.write_text(json.dumps(data))
    path = import_legacy_comparison(legacy, tmp_path / 'changed')
    assert load_manifest(path)['voices'][0]['acceptance'] is None


@pytest.mark.parametrize('field,value', [('model', 'wrong-model'), ('instructions', 'unsupported instructions')])
def test_import_rejects_mismatched_clone_track_settings(legacy, tmp_path, field, value):
    data = json.loads(legacy.read_text())
    data['voices'][0]['tracks']['cloned'][field] = value
    legacy.write_text(json.dumps(data))
    output = tmp_path / 'mismatch'
    with pytest.raises(ValueError, match='cloned|Cloned'):
        import_legacy_comparison(legacy, output)
    assert not output.exists()


@pytest.mark.parametrize('change', ['cloud-id', 'reference', 'formatting'])
def test_changed_historical_identity_does_not_inherit_approval(legacy, tmp_path, monkeypatch, change):
    import hashlib
    from tts_app.voice_tools import approved
    original = json.loads(legacy.read_text())
    monkeypatch.setattr(approved, 'APPROVED_MANIFEST_SHA256', hashlib.sha256(legacy.read_bytes()).hexdigest())
    monkeypatch.setattr(approved, 'APPROVED_REFERENCE_SHA256', {v['number']: hashlib.sha256((legacy.parent.parent / v['reference_audio']).read_bytes()).hexdigest() for v in original['voices']})
    assert approved.is_approved_legacy(legacy, original)
    if change == 'cloud-id':
        original['voices'][0]['enrollment']['voice'] = 'qwen-tts-vc-another-enrollment'
        legacy.write_text(json.dumps(original))
    elif change == 'reference':
        reference = legacy.parent.parent / original['voices'][0]['reference_audio']
        audio = bytearray(reference.read_bytes())
        audio[-1] = 1
        reference.write_bytes(audio)
    else:
        legacy.write_text(json.dumps(original, indent=2))
    assert not approved.is_approved_legacy(legacy, original)
    manifest = load_manifest(import_legacy_comparison(legacy, tmp_path / 'unapproved'))
    assert all(voice['acceptance'] is None for voice in manifest['voices'])

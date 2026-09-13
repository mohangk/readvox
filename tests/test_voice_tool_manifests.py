import hashlib
import json
from pathlib import Path

import pytest

from tts_app.voice_tools.manifest import load_manifest, save_manifest, resolve_asset


def candidate(tmp_path):
    (tmp_path / 'text.txt').write_text('Hello')
    return {'schema_version': 1, 'run_id': 'test', 'kind': 'candidates', 'samples': [],
            'text': {'path': 'text.txt', 'sha256': hashlib.sha256(b'Hello').hexdigest()}}


def test_manifest_roundtrip_and_checksum(tmp_path):
    path = tmp_path / 'manifest.json'
    data = candidate(tmp_path)
    save_manifest(path, data)
    assert load_manifest(path) == data
    (tmp_path / 'text.txt').write_text('Changed')
    with pytest.raises(ValueError, match='checksum'):
        load_manifest(path)


def test_version_and_path_rejection(tmp_path):
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps({'schema_version': 9}))
    with pytest.raises(ValueError, match='version'):
        load_manifest(path)
    for name in ('../private', '/tmp/private', 'https://example.com/a'):
        with pytest.raises(ValueError, match='relative|escape'):
            resolve_asset(path, name)
    assert resolve_asset(path, 'audio/ref.wav') == tmp_path / 'audio/ref.wav'
    (tmp_path / 'link').symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(ValueError, match='escape'):
        resolve_asset(path, 'link/private')


def test_invalid_save_leaves_previous_manifest(tmp_path):
    path = tmp_path / 'manifest.json'
    data = candidate(tmp_path)
    save_manifest(path, data)
    before = path.read_bytes()
    data['text']['sha256'] = 'bad'
    with pytest.raises(ValueError, match='SHA|checksum'):
        save_manifest(path, data)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob('*.tmp'))


def test_atomic_replace_failure_keeps_previous(tmp_path, monkeypatch):
    path = tmp_path / 'manifest.json'
    data = candidate(tmp_path)
    save_manifest(path, data)
    before = path.read_bytes()
    def fail(*args):
        raise OSError('disk failure')
    monkeypatch.setattr('tts_app.voice_tools.manifest.os.replace', fail)
    with pytest.raises(OSError):
        save_manifest(path, data | {'run_id': 'new'})
    assert path.read_bytes() == before


@pytest.mark.parametrize('settings', [
    {'voice': 'Unknown', 'model': 'qwen3-tts-instruct-flash-realtime', 'speed': 1, 'language': 'English', 'instructions': '', 'sample_rate': 24000, 'audio_format': 'pcm'},
    {'voice': 'Kai', 'model': 'wrong', 'speed': 1, 'language': 'English', 'instructions': '', 'sample_rate': 24000, 'audio_format': 'pcm'},
    {'voice': 'Kai', 'model': 'qwen3-tts-instruct-flash-realtime', 'speed': float('nan'), 'language': 'English', 'instructions': '', 'sample_rate': 24000, 'audio_format': 'pcm'},
])
def test_candidate_settings_validated_on_load(tmp_path, settings):
    data = candidate(tmp_path)
    data['samples'] = [{'number': 1, 'settings': settings, 'text_sha256': data['text']['sha256'], 'status': 'queued'}]
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_manifest(path)

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from tts_app.storage import Storage


def definition(raw='reader', **changes):
    return dict(key='builtin-'+raw, provider='qwen', provider_voice_id=raw, name=raw,
                kind='builtin', available=True, model='model-1', languages=['en', 'zh'],
                supports_instructions=True, metadata={}, **changes)


def run_cli(*args):
    env = {key: value for key, value in os.environ.items() if key not in ('QWEN_API_KEY', 'DASHSCOPE_API_KEY')}
    return subprocess.run([sys.executable, 'scripts/populate_voice_catalog.py', *args],
                          capture_output=True, text=True, env=env)


def directory_fingerprints(directory):
    # Opening/closing the main DB in this process would release SQLite's POSIX
    # locks, invalidating active-transaction tests. Inspect in another process.
    script = "import hashlib,json,pathlib,sys; print(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in pathlib.Path(sys.argv[1]).iterdir()}))"
    return json.loads(subprocess.check_output([sys.executable, '-c', script, str(directory)], text=True))


def test_check_does_not_create_target(tmp_path):
    target = tmp_path / 'new-catalog'
    result = run_cli('--provider', 'qwen', '--data-dir', str(target), '--check')
    assert result.returncode == 0, result.stderr
    assert not target.exists()
    report = json.loads(result.stdout)
    assert report['added'] and report['target_exists'] is False


def test_apply_without_credentials_and_repeat_is_noop(tmp_path):
    target = tmp_path / 'new-catalog'
    first = run_cli('--data-dir', str(target))
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)['added']
    storage = Storage(target / 'app.db')
    before = storage.list_voices()
    second = run_cli('--data-dir', str(target))
    assert second.returncode == 0, second.stderr
    report = json.loads(second.stdout)
    assert not report['added'] and not report['updated'] and not report['retired']
    assert storage.list_voices() == before
    assert storage.list_voice_profiles() == []


def test_sync_scopes_refresh_and_preserves_profile_settings(unpopulated_settings):
    from tts_app.voice_catalog_sync import sync_voice_catalog
    source = [definition(), definition('retire')]
    sync_voice_catalog(unpopulated_settings, definitions=source)
    storage = Storage(unpopulated_settings.db_path)
    reader = storage.list_voices()[0]
    clone = {**definition('clone'), 'kind': 'cloned'}
    other = {**definition('other'), 'provider': 'other'}
    untouched = storage.install_voices([clone, other])
    profile = storage.save_voice_profile(dict(name='Reading', voice_id=reader['id'], language='en',
        speed=1.25, instructions='Calm', preview_text='Sample'))
    changed = {**source[0], 'model': 'model-2', 'supports_instructions': False, 'languages': ['en'], 'metadata': {'revision': 2}}
    report = sync_voice_catalog(unpopulated_settings, definitions=[changed, definition('new')])
    assert report['added'] == ['builtin-new'] and report['updated'] == ['builtin-reader']
    assert report['retired'] == ['builtin-retire']
    assert report['model_changes'] == [dict(key='builtin-reader', id=reader['id'], before='model-1', after='model-2')]
    assert storage.get_voice(reader['id'])['metadata'] == {'revision': 2}
    assert storage.get_voice_profile(profile['id']) == profile
    assert [storage.get_voice(value['id']) for value in untouched] == untouched
    report = sync_voice_catalog(unpopulated_settings, definitions=source)
    assert 'builtin-retire' in report['updated']


def test_invalid_sources_and_late_collision_are_atomic(unpopulated_settings):
    from tts_app.voice_catalog_sync import sync_voice_catalog
    sync_voice_catalog(unpopulated_settings, definitions=[definition()])
    storage = Storage(unpopulated_settings.db_path)
    storage.install_voices([{**definition('clone'), 'kind': 'cloned'}])
    before = unpopulated_settings.db_path.read_bytes()
    for values in ([], [definition(), definition()], [definition('new'), definition('clone')]):
        with pytest.raises(ValueError):
            sync_voice_catalog(unpopulated_settings, definitions=values)
        assert unpopulated_settings.db_path.read_bytes() == before


def test_reviewed_source_has_one_binding_and_identity_per_preset():
    from tts_app.providers.qwen_catalog import qwen_voice_definitions, INSTRUCTION_MODEL, FLASH_MODEL
    voices = qwen_voice_definitions()
    assert len(voices) == len({value['provider_voice_id'] for value in voices}) == 48
    by_name = {value['name']: value for value in voices}
    assert by_name['Kai']['model'] == INSTRUCTION_MODEL and by_name['Kai']['supports_instructions']
    assert by_name['Jennifer']['model'] == FLASH_MODEL and not by_name['Jennifer']['supports_instructions']
    assert by_name['Kai']['languages'] == by_name['Jennifer']['languages'] == ['en','zh']
    assert by_name['Jada']['languages'] == ['en']


def test_invalid_source_never_creates_absent_target(unpopulated_settings):
    from tts_app.voice_catalog_sync import sync_voice_catalog
    values = [definition(), {**definition('second'), 'key': definition()['key']}]
    for source in ([], values, [definition(), {**definition(), 'key': 'different-key'}]):
        with pytest.raises(ValueError):
            sync_voice_catalog(unpopulated_settings, definitions=source)
        assert not unpopulated_settings.data_dir.exists()


def test_check_refuses_checkpoint_capable_wal_connection_without_changing_files(unpopulated_settings):
    from tts_app.voice_catalog_sync import sync_voice_catalog
    sync_voice_catalog(unpopulated_settings, definitions=[definition()])
    conn = sqlite3.connect(unpopulated_settings.db_path)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute("UPDATE voices SET name='WAL name'")
        conn.commit()
        before = directory_fingerprints(unpopulated_settings.data_dir)
        with pytest.raises(ValueError, match='Close.*connections'):
            sync_voice_catalog(unpopulated_settings, check_only=True, definitions=[definition()])
        assert directory_fingerprints(unpopulated_settings.data_dir) == before
    finally:
        conn.close()


def test_invalid_runtime_provider_rejected_before_target_creation(unpopulated_settings):
    from dataclasses import replace
    from tts_app.voice_catalog_sync import sync_voice_catalog
    with pytest.raises(ValueError, match='unknown TTS provider'):
        sync_voice_catalog(replace(unpopulated_settings, provider_name='typo-provider'))
    assert not unpopulated_settings.data_dir.exists()


@pytest.mark.parametrize('mode', ['DELETE', 'WAL'])
def test_check_refuses_open_transaction_without_changing_files(unpopulated_settings, mode):
    from tts_app.voice_catalog_sync import sync_voice_catalog
    sync_voice_catalog(unpopulated_settings, definitions=[definition()])
    conn = sqlite3.connect(unpopulated_settings.db_path)
    try:
        conn.execute('PRAGMA journal_mode=' + mode)
        conn.execute('BEGIN IMMEDIATE')
        conn.execute("UPDATE voices SET name='uncommitted'")
        before = directory_fingerprints(unpopulated_settings.data_dir)
        with pytest.raises(ValueError, match='Close.*connections'):
            sync_voice_catalog(unpopulated_settings, check_only=True, definitions=[definition()])
        assert directory_fingerprints(unpopulated_settings.data_dir) == before
    finally:
        conn.close()


def test_check_recovers_hot_rollback_journal_only_in_private_copy(unpopulated_settings):
    from tts_app.voice_catalog_sync import sync_voice_catalog
    sync_voice_catalog(unpopulated_settings, definitions=[definition()])
    script = '''import os, sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute('PRAGMA journal_mode=DELETE')
conn.execute('PRAGMA cache_size=5')
conn.execute('CREATE TABLE padding(value BLOB)')
conn.executemany('INSERT INTO padding VALUES(?)', [(bytes(4000),)] * 100)
conn.commit()
conn.execute('BEGIN IMMEDIATE')
conn.execute("UPDATE voices SET name='uncommitted crash'")
conn.execute('UPDATE padding SET value=zeroblob(4001)')
os._exit(0)
'''
    subprocess.run([sys.executable, '-c', script, str(unpopulated_settings.db_path)], check=True)
    assert Path(str(unpopulated_settings.db_path) + '-journal').exists()
    before = directory_fingerprints(unpopulated_settings.data_dir)
    report = sync_voice_catalog(unpopulated_settings, check_only=True, definitions=[definition()])
    assert report['unchanged'] == ['builtin-reader'] and report['updated'] == []
    assert directory_fingerprints(unpopulated_settings.data_dir) == before


def test_check_reads_committed_wal_after_writer_exits_without_checkpoint(unpopulated_settings):
    from tts_app.voice_catalog_sync import sync_voice_catalog
    sync_voice_catalog(unpopulated_settings, definitions=[definition()])
    script = '''import os, sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute('PRAGMA journal_mode=WAL')
conn.execute("UPDATE voices SET name='committed WAL name'")
conn.commit()
os._exit(0)
'''
    subprocess.run([sys.executable, '-c', script, str(unpopulated_settings.db_path)], check=True)
    assert Path(str(unpopulated_settings.db_path) + '-wal').stat().st_size > 0
    before = directory_fingerprints(unpopulated_settings.data_dir)
    report = sync_voice_catalog(unpopulated_settings, check_only=True, definitions=[definition()])
    assert report['updated'] == ['builtin-reader']
    assert directory_fingerprints(unpopulated_settings.data_dir) == before


@pytest.mark.parametrize('check', [False, True])
def test_cli_invalid_config_preserves_existing_database(unpopulated_settings, monkeypatch, check):
    from tts_app.voice_catalog_sync import sync_voice_catalog
    sync_voice_catalog(unpopulated_settings, definitions=[definition()])
    before = directory_fingerprints(unpopulated_settings.data_dir)
    monkeypatch.setenv('TTS_PROVIDER', 'typo-provider')
    args = ['--provider', 'qwen', '--data-dir', str(unpopulated_settings.data_dir)]
    result = run_cli(*args, *(['--check'] if check else []))
    assert result.returncode == 1
    assert 'unknown TTS provider' in result.stderr
    assert directory_fingerprints(unpopulated_settings.data_dir) == before


@pytest.mark.parametrize('check_only', [False, True])
def test_unsupported_schema_check_and_apply_leave_target_unchanged(unpopulated_settings, check_only):
    from tts_app.voice_catalog_sync import sync_voice_catalog
    unpopulated_settings.data_dir.mkdir()
    with sqlite3.connect(unpopulated_settings.db_path) as conn:
        conn.execute('CREATE TABLE voice_profiles(id INTEGER PRIMARY KEY, voice TEXT, model TEXT)')
    before = directory_fingerprints(unpopulated_settings.data_dir)
    with pytest.raises(ValueError, match='Unsupported voice schema'):
        sync_voice_catalog(unpopulated_settings, check_only=check_only, definitions=[definition()])
    assert directory_fingerprints(unpopulated_settings.data_dir) == before


def test_check_current_catalog_preserves_profiles_markers_and_media(unpopulated_settings):
    from tts_app.voice_catalog_sync import sync_voice_catalog
    sync_voice_catalog(unpopulated_settings, definitions=[definition()])
    storage = Storage(unpopulated_settings.db_path)
    selected = storage.list_voices()[0]
    storage.initialize_voice_profiles([dict(name='Reading', voice_id=selected['id'], language='en',
        speed=1.25, instructions='Calm', preview_text='Sample')])
    asset = unpopulated_settings.data_dir / 'reference.wav'
    asset.write_bytes(b'retained reference')
    before = directory_fingerprints(unpopulated_settings.data_dir)
    report = sync_voice_catalog(unpopulated_settings, check_only=True,
        definitions=[{**definition(), 'name':'Updated'}, definition('new')])
    assert report['added'] == ['builtin-new']
    assert report['updated'] == ['builtin-reader']
    assert directory_fingerprints(unpopulated_settings.data_dir) == before

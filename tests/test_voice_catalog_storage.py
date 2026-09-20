import sqlite3

import pytest

from tts_app.storage import Storage


def voice(provider='other', key='other-reader', kind='builtin'):
    return dict(key=key,provider=provider,provider_voice_id='reader',name='Reader',kind=kind,available=True,
                model='reading-v1',languages=['en'],supports_instructions=True,metadata={})


def profile(voice_id, name='Reading'):
    return dict(voice_id=voice_id,name=name,language='en',speed=1.1,instructions='Calm',preview_text='A passage.')


def test_catalog_supports_generic_providers_and_profiles_share_voice(tmp_path):
    storage=Storage(tmp_path/'app.db');storage.init_schema()
    storage.sync_provider_voices('other',[voice()])
    saved_voice=storage.list_voices('other')[0]
    first=storage.save_voice_profile(profile(saved_voice['id']))
    second=storage.save_voice_profile(profile(saved_voice['id'],'Faster reading'))
    assert first['voice_id']==second['voice_id']==saved_voice['id']
    assert first['provider']=='other' and first['voice']=='reader'
    assert first['voice_name']=='Reader'
    storage.delete_voice_profile(first['id']);storage.delete_voice_profile(second['id'])
    storage.init_schema();storage.sync_provider_voices('other',[voice()])
    assert storage.list_voice_profiles()==[]
    assert storage.list_voices('other')[0]['id']==saved_voice['id']


def test_retired_builtin_is_preserved_and_can_return(tmp_path):
    storage=Storage(tmp_path/'app.db');storage.init_schema();storage.sync_provider_voices('other',[voice()])
    selected=storage.list_voices('other')[0];saved=storage.save_voice_profile(profile(selected['id']))
    storage.sync_provider_voices('other',[{**voice(), 'key':'replacement', 'provider_voice_id':'replacement'}])
    assert storage.get_voice(selected['id'])['available'] is False
    assert storage.get_voice_profile(saved['id'])['voice_id']==selected['id']
    storage.sync_provider_voices('other',[voice()])
    assert storage.get_voice(selected['id'])['available'] is True


def test_profile_cannot_reference_missing_voice(tmp_path):
    storage=Storage(tmp_path/'app.db');storage.init_schema()
    with pytest.raises((KeyError,sqlite3.IntegrityError)):
        storage.save_voice_profile(profile(999))


def test_catalog_install_is_atomic_and_never_recreates_profiles(tmp_path):
    storage=Storage(tmp_path/'app.db');storage.init_schema()
    original=storage.install_voices([voice(kind='cloned')])[0]
    saved=storage.save_voice_profile(profile(original['id']))
    storage.save_voice_profile({**saved,'speed':1.5},saved['id'])
    storage.delete_voice_profile(saved['id'])
    assert storage.install_voices([voice(kind='cloned')])==[original]
    assert storage.list_voice_profiles()==[]
    new={**voice(kind='cloned'),'key':'new-voice','provider_voice_id':'new-reader'}
    with pytest.raises(ValueError,match='different settings'):
        storage.install_voices([new,{**voice(kind='cloned'),'name':'Changed identity'}])
    assert storage.list_voices()==[original]


def test_profiles_share_bilingual_voice_without_owning_model(tmp_path):
    storage = Storage(tmp_path / 'app.db')
    storage.init_schema()
    definition = dict(key='bilingual', provider='other', provider_voice_id='bilingual',
                      name='Bilingual', kind='builtin', available=True, model='reading-v1',
                      languages=['en', 'zh'], supports_instructions=True, metadata={})
    voice = storage.install_voices([definition])[0]
    for language in ('en', 'zh'):
        saved = storage.save_voice_profile(dict(name=language, voice_id=voice['id'],
            language=language, speed=1.1, instructions='', preview_text='Sample'))
        assert 'model' not in saved
        assert saved['voice_id'] == voice['id']
    assert storage.list_voices() == [voice]
    assert voice['languages'] == ['en', 'zh']
    with storage.connection() as conn:
        assert 'model' not in {row['name'] for row in conn.execute('PRAGMA table_info(voice_profiles)')}
        assert 'models_json' not in {row['name'] for row in conn.execute('PRAGMA table_info(voices)')}




def test_current_setup_preserves_catalog_profiles_history_and_seed_marker(tmp_path):
    storage = Storage(tmp_path / 'app.db')
    storage.init_schema()
    selected = storage.install_voices([voice(kind='cloned')])[0]
    defaults = [profile(selected['id'], 'Default')]
    storage.initialize_voice_profiles(defaults)
    default = storage.list_voice_profiles()[0]
    storage.delete_voice_profile(default['id'])
    saved = storage.save_voice_profile(profile(selected['id'], 'My reading'))
    generation = storage.create_generation(source_type='text', title='Saved', url=None,
        full_text='Saved audio', provider='other', voice='reader', settings={'model':'historic-model'})
    asset = tmp_path / 'reference.wav'
    asset.write_bytes(b'reusable reference')
    with storage.connection() as conn:
        # Production retains these historical markers. Only version 1 is used.
        conn.executemany('INSERT OR IGNORE INTO profile_migrations VALUES(?)', [(1,), (2,), (3,), (4,)])
        conn.execute("UPDATE sqlite_sequence SET seq=100 WHERE name='voice_profiles'")
        conn.execute("UPDATE sqlite_sequence SET seq=90 WHERE name='voices'")
    history = storage.get_generation(generation)
    storage.init_schema()
    storage.initialize_voice_profiles(defaults)
    assert storage.list_voices() == [selected]
    assert storage.list_voice_profiles() == [saved]
    assert storage.get_generation(generation) == history
    assert asset.read_bytes() == b'reusable reference'
    assert storage.save_voice_profile(profile(selected['id'], 'New'))['id'] == 101
    assert storage.install_voices([{**voice(), 'key':'new', 'provider_voice_id':'new'}])[0]['id'] == 91
    with storage.connection() as conn:
        assert [row[0] for row in conn.execute('SELECT version FROM profile_migrations ORDER BY version')] == [1, 2, 3, 4]
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []


def test_empty_catalog_can_seed_later_but_never_recreates_deleted_defaults(tmp_path):
    storage = Storage(tmp_path / 'app.db')
    storage.init_schema()
    storage.initialize_voice_profiles([])
    assert storage.list_voices() == storage.list_voice_profiles() == []
    selected = storage.install_voices([voice()])[0]
    defaults = [profile(selected['id'])]
    storage.initialize_voice_profiles(defaults)
    saved = storage.list_voice_profiles()[0]
    storage.delete_voice_profile(saved['id'])
    storage.init_schema()
    storage.initialize_voice_profiles(defaults)
    assert storage.list_voice_profiles() == []


@pytest.mark.parametrize('schema', [
    'CREATE TABLE registered_voices(system_key TEXT PRIMARY KEY)',
    'CREATE TABLE voices(id INTEGER PRIMARY KEY, models_json TEXT)',
    'CREATE TABLE voice_profiles(id INTEGER PRIMARY KEY, voice TEXT, model TEXT)',
])
def test_unsupported_voice_schema_fails_before_any_changes(tmp_path, schema):
    path = tmp_path / 'app.db'
    with sqlite3.connect(path) as conn:
        conn.execute(schema)
    before = path.read_bytes()
    with pytest.raises(ValueError, match='Unsupported voice schema'):
        Storage(path).init_schema()
    assert path.read_bytes() == before

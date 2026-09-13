import json
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


def test_migrates_system_and_personal_clone_profiles_without_changing_settings(tmp_path):
    path=tmp_path/'app.db'
    definition=dict(system_key='readvox-kai-v1',provider='qwen',model='qwen3-tts-vc-realtime-2026-01-15',voice='qwen-tts-vc-example',language='en',name='Kai Narrator',speed=1,instructions='',preview_text='Original',reference_path='voices/old/kai.wav',reference_sha256='a'*64,provenance={'selection':16})
    with sqlite3.connect(path) as conn:
        conn.executescript('''CREATE TABLE profile_migrations(version INTEGER PRIMARY KEY);
        INSERT INTO profile_migrations VALUES(1);INSERT INTO profile_migrations VALUES(2);
        CREATE TABLE registered_voices(system_key TEXT PRIMARY KEY,provider TEXT NOT NULL,definition_json TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE voice_profiles(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,name_key TEXT NOT NULL UNIQUE,model TEXT NOT NULL,voice TEXT NOT NULL,language TEXT NOT NULL,speed REAL NOT NULL,instructions TEXT NOT NULL,preview_text TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,system_key TEXT);
        CREATE TABLE retained_audio(path TEXT);INSERT INTO retained_audio VALUES('audio/42/0.mp3');''')
        conn.execute('INSERT INTO registered_voices VALUES(?,?,?,?)',(definition['system_key'],'qwen',json.dumps(definition),'yesterday'))
        for id,name,speed,key in [(5,'Kai Narrator',1,'readvox-kai-v1'),(9,'My faster Kai',1.25,None)]:
            conn.execute('INSERT INTO voice_profiles VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(id,name,name.casefold(),definition['model'],definition['voice'],'en',speed,'','My preview','created','updated',key))
    storage=Storage(path);storage.init_schema(provider_name='qwen')
    voices=storage.list_voices('qwen');profiles=storage.list_voice_profiles()
    assert len(voices)==1 and voices[0]['kind']=='cloned'
    assert [p['id'] for p in profiles]==[5,9]
    assert {p['voice_id'] for p in profiles}=={voices[0]['id']}
    assert [p['speed'] for p in profiles]==[1,1.25]
    assert all(p['created_at']=='created' and p['updated_at']=='updated' for p in profiles)
    assert voices[0]['metadata']['reference_path']=='voices/old/kai.wav'
    changed=storage.save_voice_profile({**profile(voices[0]['id']), 'model':definition['model'],'name':'Changed Kai','instructions':''},5)
    assert changed['name']=='Changed Kai'
    storage.delete_voice_profile(5);storage.init_schema(provider_name='qwen')
    assert [p['id'] for p in storage.list_voice_profiles()]==[9]
    with storage.connection() as conn:
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='registered_voices'").fetchone()
        columns={r['name'] for r in conn.execute('PRAGMA table_info(voice_profiles)')}
        assert 'voice' not in columns and 'system_key' not in columns and 'voice_id' in columns
        assert conn.execute('SELECT path FROM retained_audio').fetchone()[0]=='audio/42/0.mp3'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


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


def test_migration_preserves_autoincrement_after_deleted_profiles(tmp_path):
    path=tmp_path/'app.db'
    with sqlite3.connect(path) as conn:
        conn.executescript('''CREATE TABLE profile_migrations(version INTEGER PRIMARY KEY);
        CREATE TABLE voice_profiles(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,name_key TEXT,model TEXT,voice TEXT,language TEXT,speed REAL,instructions TEXT,preview_text TEXT,created_at TEXT,updated_at TEXT);
        INSERT INTO voice_profiles VALUES(99,'Deleted','deleted','reading-v1','reader','en',1,'','Preview','created','updated');
        DELETE FROM voice_profiles;''')
    storage=Storage(path);storage.init_schema(provider_name='other')
    storage.sync_provider_voices('other',[voice()])
    assert storage.save_voice_profile(profile(storage.list_voices('other')[0]['id']))['id']==100


def legacy_registrations(path, registrations, profiles):
    with sqlite3.connect(path) as conn:
        conn.executescript('''CREATE TABLE profile_migrations(version INTEGER PRIMARY KEY);
        INSERT INTO profile_migrations VALUES(1);INSERT INTO profile_migrations VALUES(2);
        CREATE TABLE registered_voices(system_key TEXT PRIMARY KEY,provider TEXT,definition_json TEXT,created_at TEXT);
        CREATE TABLE voice_profiles(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,name_key TEXT,model TEXT,voice TEXT,language TEXT,speed REAL,instructions TEXT,preview_text TEXT,created_at TEXT,updated_at TEXT,system_key TEXT);''')
        for key,provider in registrations:
            definition=dict(system_key=key,provider=provider,voice='same-provider-id',model='clone-model',language='en',name=key,speed=1,instructions='',preview_text='Reference',reference_path=f'voices/{key}.wav',reference_sha256='a'*64,provenance={'key':key})
            conn.execute('INSERT INTO registered_voices VALUES(?,?,?,?)',(key,provider,json.dumps(definition),'created'))
        for id,key in enumerate(profiles,1):
            conn.execute('INSERT INTO voice_profiles VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(id,'Profile '+str(id),'profile '+str(id),'clone-model','same-provider-id','en',1,'','Preview','created','updated',key))


def test_duplicate_legacy_enrollments_share_identity_and_keep_provenance(tmp_path):
    path=tmp_path/'app.db';legacy_registrations(path,[('first','qwen'),('second','qwen')],['first','second',None])
    storage=Storage(path);storage.init_schema(provider_name='qwen')
    voices=storage.list_voices();profiles=storage.list_voice_profiles()
    assert len(voices)==1 and len(profiles)==3
    assert {p['voice_id'] for p in profiles}=={voices[0]['id']}
    assert {entry['system_key'] for entry in voices[0]['metadata']['provenance']['legacy_registrations']}=={'first','second'}


def test_legacy_profile_marker_and_provider_prevent_cross_provider_binding(tmp_path):
    path=tmp_path/'app.db';legacy_registrations(path,[('qwen-one','qwen'),('fake-one','fake')],['qwen-one','fake-one',None])
    storage=Storage(path);storage.init_schema(provider_name='qwen')
    profiles=storage.list_voice_profiles()
    assert [p['provider'] for p in profiles]==['qwen','fake','qwen']


def test_invalid_provider_never_commits_profile_migration(unpopulated_settings):
    from dataclasses import replace
    from tts_app.api import create_app
    unpopulated_settings.data_dir.mkdir()
    legacy_registrations(unpopulated_settings.db_path,[],[None])
    before=unpopulated_settings.db_path.read_bytes()
    with pytest.raises(ValueError,match='unknown TTS provider'):
        create_app(replace(unpopulated_settings,provider_name='typo-provider'))
    assert unpopulated_settings.db_path.read_bytes()==before


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


def old_catalog(path):
    with sqlite3.connect(path) as conn:
        conn.executescript('''CREATE TABLE profile_migrations(version INTEGER PRIMARY KEY);
        INSERT INTO profile_migrations VALUES(1); INSERT INTO profile_migrations VALUES(3);
        CREATE TABLE voices(id INTEGER PRIMARY KEY AUTOINCREMENT,key TEXT UNIQUE,provider TEXT,provider_voice_id TEXT,
            name TEXT,kind TEXT,available INTEGER,models_json TEXT,metadata_json TEXT,created_at TEXT,updated_at TEXT);
        CREATE TABLE voice_profiles(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,name_key TEXT UNIQUE,
            voice_id INTEGER REFERENCES voices(id),model TEXT,language TEXT,speed REAL,instructions TEXT,
            preview_text TEXT,created_at TEXT,updated_at TEXT);
        CREATE TABLE historical_snapshots(id INTEGER PRIMARY KEY,settings_json TEXT);
        INSERT INTO historical_snapshots VALUES(42,'{"model":"historic-model","voice":"Kai"}');''')
        for id,raw,kind,models in [
            (5,'Kai','builtin',{'qwen3-tts-flash-realtime':dict(label='Flash',languages=['en','zh'],supports_instructions=False)}),
            (9,'clone','cloned',{'enrolled-model':dict(label='Clone',languages=['en'],supports_instructions=False)}),
            (12,'unknown','builtin',{}),
        ]:
            from tts_app.voice_storage import builtin_voice_key
            conn.execute('INSERT INTO voices VALUES(?,?,?,?,?,?,?,?,?,?,?)', (id,builtin_voice_key('qwen',raw),'qwen',raw,
                raw,kind,1,json.dumps(models),json.dumps({'reference_path':'voices/reference.wav'}),'voice-created','voice-updated'))
        for id,voice_id,model,language,instructions in [
            (10,5,'qwen3-tts-flash-realtime','en','Calm'),
            (11,5,'qwen3-tts-flash-realtime','zh',''),
            (14,9,'enrolled-model','en',''),
            (15,9,'enrolled-model','zh',''),
            (16,9,'enrolled-model','en','Calm'),
            (18,12,'unknown','en',''),
        ]:
            conn.execute('INSERT INTO voice_profiles VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (id,str(id),str(id),voice_id,model,language,1.25,instructions,'Sample','profile-created','profile-updated'))
        conn.execute("UPDATE sqlite_sequence SET seq=100 WHERE name='voice_profiles'")
        conn.execute("UPDATE sqlite_sequence SET seq=90 WHERE name='voices'")


def test_forward_migration_reports_cleanup_preserves_ids_snapshots_and_assets(tmp_path):
    path=tmp_path/'app.db'; old_catalog(path)
    asset=tmp_path/'reference.wav'; asset.write_bytes(b'reusable reference')
    storage=Storage(path); storage.init_schema()
    report=storage.voice_migration_report
    assert [(item['id'],item['reason']) for item in report['deleted_profiles']]==[
        (15,'Language is unsupported by the voice'), (16,'Instructions are unsupported by the voice'),
        (18,'Unresolvable voice identity or model binding')]
    assert [item['id'] for item in report['deleted_voices']]==[12]
    assert {item['id'] for item in report['model_changes'] if item['table']=='voice_profiles'}=={10,11}
    assert [voice['id'] for voice in storage.list_voices()]==[5,9]
    assert [profile['id'] for profile in storage.list_voice_profiles()]==[10,11,14]
    assert all(profile['speed']==1.25 and profile['updated_at']=='profile-updated' and 'model' not in profile
               for profile in storage.list_voice_profiles())
    assert asset.read_bytes()==b'reusable reference'
    with storage.connection() as conn:
        assert conn.execute('SELECT settings_json FROM historical_snapshots').fetchone()[0]=='{"model":"historic-model","voice":"Kai"}'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    created=storage.save_voice_profile({**profile(5),'name':'New'})
    assert created['id']==101
    new_voice=storage.install_voices([voice()])[0]
    assert new_voice['id']==91
    storage.init_schema()
    assert storage.voice_migration_report['schema_upgraded'] is False


def test_forward_migration_rolls_back_on_late_conflict(tmp_path):
    from tts_app.voice_migrations import migrate_voice_catalog
    from tts_app.voice_storage import reconcile_provider_voices
    path=tmp_path/'app.db'; old_catalog(path)
    before=path.read_bytes()
    storage=Storage(path)
    with pytest.raises(ValueError,match='conflicts'):
        with storage.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            migrate_voice_catalog(conn,'qwen')
            reconcile_provider_voices(conn,'qwen',[{**voice(provider='qwen'), 'provider_voice_id':'clone'}])
    assert path.read_bytes()==before


def test_migration_rejects_invalid_reviewed_source_before_cleanup(tmp_path, monkeypatch):
    from tts_app.providers import qwen_catalog
    path=tmp_path/'app.db'; old_catalog(path)
    before=path.read_bytes()
    monkeypatch.setattr(qwen_catalog,'qwen_voice_definitions',lambda: [])
    with pytest.raises(ValueError,match='empty'):
        Storage(path).init_schema()
    assert path.read_bytes()==before

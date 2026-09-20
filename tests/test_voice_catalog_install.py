import json
import wave

import pytest

from tts_app.storage import Storage


@pytest.fixture
def source(tmp_path):
    import hashlib
    from tts_app.voice_tools.manifest import save_manifest

    run = tmp_path / 'workshop'
    run.mkdir()
    text = run / 'passage.txt'
    text.write_text('A comparison passage.')

    def asset(path):
        return {'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    voices = []
    for name, speed in [('Kai', 1), ('Vivian', 1.1), ('Bellona', 1.25), ('Neil', 1)]:
        audio = run / f'{name.lower()}-reference.wav'
        with wave.open(str(audio), 'wb') as wav:
            wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0\0' * 72000)
        key = f'readvox-{name.lower()}-v1'
        settings = dict(model='qwen3-tts-vc-realtime-2026-01-15', voice=f'qwen-tts-vc-test-{name}',
                        language='English', speed=speed, instructions='', audio_format='pcm', sample_rate=24000)
        voices.append(dict(
            key=key, name=f'{name} Narrator', language='en', speed=speed,
            reference={**asset(audio), 'provenance': {'text': asset(text)}},
            enrollment={'voice': settings['voice'], 'target_model': settings['model']},
            acceptance={'key': key, 'speed': speed, 'source': 'operator'},
            comparisons=[dict(id=f'comparison-{name.lower()}', mode='cloned', settings=settings,
                              status='completed', audio=asset(audio),
                              passages=[dict(text=asset(text), audio=asset(audio), status='completed', duration=3)],
                              boundaries=[0], duration=3,
                              input_identity={'mode': 'cloned', 'settings': settings,
                                              'passage_hashes': [asset(text)['sha256']]})]))
    path = run / 'manifest.json'
    save_manifest(path, {'schema_version': 1, 'kind': 'voice', 'run_id': 'narrators-v1', 'voices': voices})
    return path


def test_install_requires_versioned_voice_manifest(unpopulated_settings, source):
    from tts_app.voice_catalog_install import install_clone_manifest
    data = json.loads(source.read_text())
    del data['schema_version']
    source.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='schema version'):
        install_clone_manifest(source, settings=unpopulated_settings)
    assert not unpopulated_settings.data_dir.exists()


def test_offline_check_writes_nothing_then_install_is_idempotent(unpopulated_settings, source):
    from tts_app.voice_catalog_install import install_clone_manifest
    checked = install_clone_manifest(source, settings=unpopulated_settings, check_only=True)
    assert len(checked) == 4
    assert not unpopulated_settings.data_dir.exists()
    original=source.read_bytes()
    profiles=install_clone_manifest(source, settings=unpopulated_settings)
    assert [p['name'] for p in profiles] == ['Kai Narrator','Vivian Narrator','Bellona Narrator','Neil Narrator']
    assert all('speed' not in voice for voice in profiles)
    assert Storage(unpopulated_settings.db_path).list_voice_profiles()==[]
    assert install_clone_manifest(source, settings=unpopulated_settings) == profiles
    storage=Storage(unpopulated_settings.db_path)
    for voice in storage.list_voices('qwen'):
        assert (unpopulated_settings.data_dir/voice['metadata']['reference_path']).read_bytes() == (source.parent/'kai-reference.wav').read_bytes()
    assert source.read_bytes() == original


@pytest.mark.parametrize('change', ['model','voice','missing','escape','fallback','speed','duplicate'])
def test_invalid_source_never_changes_database_or_copies(unpopulated_settings, source, change):
    from tts_app.voice_catalog_install import install_clone_manifest
    data=json.loads(source.read_text());voice=data['voices'][0]
    if change=='model': voice['comparisons'][0]['settings']['model']='wrong'
    if change=='voice': voice['enrollment']['voice']=''
    if change=='missing': voice['reference']['path']='missing.wav'
    if change=='escape': voice['reference']['path']='../outside.wav'
    if change=='fallback': voice['enrollment']['fallback_mode']=True
    if change=='speed': voice['acceptance']['speed']=1.25
    if change=='duplicate': data['voices'].append(voice)
    source.write_text(json.dumps(data))
    with pytest.raises((ValueError,FileNotFoundError)):
        install_clone_manifest(source,settings=unpopulated_settings)
    assert not unpopulated_settings.data_dir.exists()


def test_profile_names_do_not_conflict_with_catalog_names(unpopulated_settings, source):
    from tts_app.voice_catalog_install import install_clone_manifest
    storage=Storage(unpopulated_settings.db_path);storage.init_schema()
    from tts_app.providers.qwen_catalog import qwen_voice_definitions
    voice=storage.install_voices([next(value for value in qwen_voice_definitions() if value['name']=='Kai')])[0]
    personal=storage.save_voice_profile(dict(name='KAI NARRATOR',voice_id=voice['id'],speed=1,language='en',instructions='',preview_text='Personal'))
    before = unpopulated_settings.db_path.read_bytes()
    assert len(install_clone_manifest(source, settings=unpopulated_settings, check_only=True)) == 4
    assert unpopulated_settings.db_path.read_bytes() == before
    assert storage.list_voice_profiles() == [personal]
    installed=install_clone_manifest(source,settings=unpopulated_settings)
    assert len(installed)==4
    assert storage.list_voice_profiles()==[personal]
    assert (unpopulated_settings.data_dir/'voices').exists()


def test_db_failure_retains_recoverable_assets_and_does_not_touch_source(unpopulated_settings, source, monkeypatch):
    from tts_app.voice_catalog_install import install_clone_manifest
    def fail(*args): raise RuntimeError('SQLite write failed')
    monkeypatch.setattr(Storage,'install_voices',fail)
    with pytest.raises(RuntimeError,match='SQLite write failed'):
        install_clone_manifest(source,settings=unpopulated_settings)
    assert list((unpopulated_settings.data_dir/'voices').glob('*/source.json'))
    assert source.exists()


@pytest.fixture
def workshop(source):
    import hashlib
    from tts_app.voice_tools.manifest import save_manifest
    run=source.parent
    def asset(path): return {'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    text=run/'passage.txt';text.write_text('A comparison passage.')
    audio=run/'kai-reference.wav'
    settings=dict(model='qwen3-tts-vc-realtime-2026-01-15',voice='qwen-tts-vc-test-kai',language='English',speed=1.0,instructions='',audio_format='pcm',sample_rate=24000,pitch=1.0,volume=1.0)
    manifest={'schema_version':1,'kind':'voice','run_id':'new-run','voices':[dict(
        key='readvox-kai-v2',name='New Kai',language='en',speed=1.0,
        reference={**asset(audio),'provenance':{}},
        enrollment={'voice':settings['voice'],'target_model':settings['model']},acceptance=None,
        comparisons=[dict(id='comparison-1',mode='cloned',settings=settings,status='completed',audio=asset(audio),
                          passages=[dict(text=asset(text),audio=asset(audio),status='completed',duration=3)],boundaries=[0],duration=3,
                          input_identity={'mode':'cloned','settings':settings,'passage_hashes':[asset(text)['sha256']]})]) ]}
    path=run/'workshop.json';save_manifest(path,manifest)
    return path


def test_workshop_requires_acceptance_and_tested_matching_settings(unpopulated_settings, workshop):
    from tts_app.voice_catalog_install import install_clone_manifest
    with pytest.raises(ValueError,match='accept'):
        install_clone_manifest(workshop,settings=unpopulated_settings,check_only=True)
    with pytest.raises(ValueError,match='completed matching'):
        install_clone_manifest(workshop,settings=unpopulated_settings,accepted_keys=['readvox-kai-v2'],speed=1.25)
    assert not unpopulated_settings.data_dir.exists()
    result=install_clone_manifest(workshop,settings=unpopulated_settings,accepted_keys=['readvox-kai-v2'],speed=1)
    assert result[0]['key']=='readvox-kai-v2'
    assert result[0]['metadata']['provenance']['acceptance']['speed']==1


def test_install_cli_dry_run_and_acceptance_are_idempotent(unpopulated_settings, workshop, monkeypatch):
    from tts_app.voice_tools.cli import main
    monkeypatch.setenv('TTS_DATA_DIR',str(unpopulated_settings.data_dir))
    args=['install','--manifest',str(workshop),'--accept','readvox-kai-v2','--speed','1']
    source=workshop.read_bytes()
    assert main(args+['--check'])==0
    assert workshop.read_bytes()==source and not unpopulated_settings.data_dir.exists()
    assert main(args)==0
    accepted=workshop.read_bytes()
    assert json.loads(accepted)['voices'][0]['acceptance']['accepted_at']
    assert main(args)==0
    assert workshop.read_bytes()==accepted


def test_modified_reference_is_rejected(unpopulated_settings, source):
    from tts_app.voice_catalog_install import install_clone_manifest
    reference=source.parent/'kai-reference.wav'
    reference.write_bytes(reference.read_bytes()+b'tampered')
    with pytest.raises(ValueError,match='checksum'):
        install_clone_manifest(source,settings=unpopulated_settings,check_only=True)
    assert not unpopulated_settings.data_dir.exists()


def test_existing_bundle_tamper_is_not_overwritten(unpopulated_settings, source):
    from tts_app.voice_catalog_install import install_clone_manifest
    profiles=install_clone_manifest(source,settings=unpopulated_settings)
    reference=next((unpopulated_settings.data_dir/'voices').glob('*/readvox-kai-v1.wav'))
    reference.write_bytes(b'changed')
    with pytest.raises(ValueError,match='refusing to overwrite'):
        install_clone_manifest(source,settings=unpopulated_settings)
    assert reference.read_bytes()==b'changed'
    assert Storage(unpopulated_settings.db_path).list_voices('qwen')==profiles


def test_installing_one_voice_then_remaining_voices_reuses_bundle(unpopulated_settings, source):
    from tts_app.voice_catalog_install import install_clone_manifest
    first=install_clone_manifest(source,settings=unpopulated_settings,accepted_keys=['readvox-kai-v1'])
    all_profiles=install_clone_manifest(source,settings=unpopulated_settings)
    assert first[0]==all_profiles[0]
    assert len(all_profiles)==4


def test_incremental_workshop_acceptance_preserves_original_registration(unpopulated_settings, workshop, monkeypatch):
    from copy import deepcopy
    from tts_app.voice_tools.cli import main
    from tts_app.voice_tools.manifest import load_manifest, save_manifest
    data=load_manifest(workshop)
    second=deepcopy(data['voices'][0]);second['key']='readvox-neil-v2';second['name']='New Neil'
    second['enrollment']['voice']='qwen-tts-vc-test-neil'
    track=second['comparisons'][0];track['id']='comparison-2'
    track['settings']['voice']=second['enrollment']['voice']
    track['input_identity']['settings']['voice']=second['enrollment']['voice']
    data['voices'].append(second);save_manifest(workshop,data)
    monkeypatch.setenv('TTS_DATA_DIR',str(unpopulated_settings.data_dir))
    args=['install','--manifest',str(workshop)]
    assert main(args+['--accept','readvox-kai-v2'])==0
    storage=Storage(unpopulated_settings.db_path)
    first=storage.list_voices('qwen')[0]
    assert main(args+['--accept','readvox-neil-v2'])==0
    profiles=storage.list_voice_profiles()
    assert main(args+['--accept','readvox-kai-v2'])==0
    assert main(args)==0
    assert storage.list_voice_profiles()==profiles
    assert next(v for v in storage.list_voices('qwen') if v['key']==first['key'])==first
    changed=load_manifest(workshop);changed['voices'][0]['name']='Different Kai';save_manifest(workshop,changed)
    assert main(args+['--accept','readvox-kai-v2'])==1
    assert storage.list_voice_profiles()==profiles


def test_db_initialization_failure_reports_retained_bundle(unpopulated_settings, source, monkeypatch, caplog):
    from tts_app.voice_catalog_install import install_clone_manifest
    def fail(*args,**kwargs): raise RuntimeError('schema locked')
    monkeypatch.setattr(Storage,'init_schema',fail)
    with pytest.raises(RuntimeError,match='schema locked'):
        install_clone_manifest(source,settings=unpopulated_settings)
    bundle=next((unpopulated_settings.data_dir/'voices').glob('*/source.json')).parent
    assert 'retained_bundle='+str(bundle) in caplog.text


@pytest.mark.parametrize('asset', ['reference', 'source'])
def test_incremental_install_checks_original_bundle(unpopulated_settings, workshop, monkeypatch, asset):
    from tts_app.voice_tools.cli import main
    from tts_app.voice_tools.manifest import load_manifest, save_manifest
    monkeypatch.setenv('TTS_DATA_DIR',str(unpopulated_settings.data_dir))
    args=['install','--manifest',str(workshop),'--accept','readvox-kai-v2']
    assert main(args)==0
    voice=Storage(unpopulated_settings.db_path).list_voices('qwen')[0]
    data=load_manifest(workshop);data['notes']='Extra workshop note';save_manifest(workshop,data)
    reference=unpopulated_settings.data_dir/voice['metadata']['reference_path']
    target=reference if asset=='reference' else reference.parent/'source.json'
    target.write_bytes(b'changed')
    assert main(args+['--check'])==1
    assert target.read_bytes()==b'changed'

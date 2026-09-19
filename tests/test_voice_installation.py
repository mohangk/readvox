from copy import deepcopy
import pytest
from tts_app.storage import Storage
from tts_app.voice_installation import validate_clone_installation

@pytest.fixture
def storage(tmp_path):
    result=Storage(tmp_path/'app.db');result.init_schema();return result

@pytest.fixture
def definition():
    return dict(key='readvox-kai-v1',provider='fake',model='qwen3-tts-vc-realtime-2026-01-15',voice='test-enrolled-kai',language='en',name='Kai Narrator',speed=1,instructions='',preview_text='Reference',reference_path='voices/test/reference.wav',reference_sha256='a'*64,provenance={'source_run_id':'narrators-v1'})

@pytest.mark.parametrize('field,value', [
    ('key', '../bad'), ('name', ' '), ('speed', float('nan')), ('speed', True),
    ('language', 'zh'), ('model', 'unregistered-model'), ('instructions', 'unsupported'),
    ('reference_path', '../outside.wav'), ('reference_sha256', 'bad'), ('voice', ''),
    ('preview_text', ' '),
])
def test_invalid_definitions_do_not_write(storage, definition, field, value):
    broken = deepcopy(definition)
    broken[field] = value
    with pytest.raises(ValueError):
        validate_clone_installation(broken)
    assert storage.list_voice_profiles() == []


def test_non_json_native_provenance_is_rejected_without_writes(storage, definition):
    with pytest.raises(ValueError, match='JSON-native'):
        validate_clone_installation({**definition, 'provenance': {'tuple': (1, 2)}})
    assert storage.list_voices('fake') == []


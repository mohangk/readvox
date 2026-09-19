import json
import wave

import pytest

from tts_app.providers.base import AudioChunk, ProviderError
from tts_app.providers.qwen_enrollment import CLONE_MODEL
from tts_app.voice_tools.cli import main
from tts_app.voice_tools.manifest import load_manifest


class Speech:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    async def stream_speech(self, text, options):
        self.calls.append((text, options))
        if len(self.calls) == self.fail_at:
            raise ProviderError('<private failure>')
        yield AudioChunk(b'\0\0' * 72000, 'application/octet-stream', 'bin')


class Enrollment:
    endpoint_region = 'dashscope-intl.aliyuncs.com'
    account_fingerprint = 'credential-fingerprint'
    target_model = CLONE_MODEL

    def __init__(self, uncertain=False):
        self.calls = 0
        self.uncertain = uncertain

    async def create(self, path, name):
        self.calls += 1
        pending = json.loads((path.parent / 'manifest.json').read_text())['voices'][0]
        assert pending['status'] == 'enrolling' and pending['preferred_name'] == name
        if self.uncertain:
            raise TimeoutError('timeout')
        return {'voice': 'qwen-tts-vc-example', 'target_model': CLONE_MODEL, 'preferred_name': name,
                'endpoint_region': self.endpoint_region, 'account_fingerprint': self.account_fingerprint}

    async def lookup(self, **kwargs):
        return {'voice_list': [{'voice': 'qwen-tts-vc-example', 'target_model': CLONE_MODEL}]}


def wav(tmp_path):
    path = tmp_path / 'input.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\0\0' * 72000)
    return path


def enroll_args(tmp_path):
    return ['enroll', '--reference', str(wav(tmp_path)), '--name', '<Kai Narrator>', '--key', 'readvox-kai-v2', '--output', str(tmp_path / 'enrolled')]


def test_candidate_matrix_dryrun_resume_and_validation(tmp_path):
    text = tmp_path / 'text.txt'
    text.write_text('A passage independent of history.')
    output = tmp_path / 'samples'
    args = ['candidates', '--text', str(text), '--voices', 'Kai', 'Neil', '--speeds', '1', '1.1', '--output', str(output)]
    provider = Speech(fail_at=2)
    assert main(args + ['--check'], provider=provider) == 0
    assert not output.exists() and not provider.calls
    assert main(args, provider=provider) == 1
    manifest = load_manifest(output / 'manifest.json')
    assert len(manifest['samples']) == 4
    assert [s['status'] for s in manifest['samples']] == ['completed', 'failed', 'completed', 'completed']
    assert len(provider.calls) == 4
    assert main(args, provider=provider) == 1
    assert len(provider.calls) == 4
    assert main(args + ['--resume', str(output / 'manifest.json')], provider=provider) == 0
    assert len(provider.calls) == 5
    text.write_text('Changed input')
    assert main(args + ['--resume', str(output / 'manifest.json')], provider=provider) == 1
    assert len(provider.calls) == 5
    assert main(['candidates', '--text', str(text), '--voices', 'Unknown', '--speeds', '1', '--output', str(tmp_path / 'invalid')], provider=provider) == 1
    assert not (tmp_path / 'invalid').exists()


def test_supplied_enrollment_comparison_separate_requests_and_report(tmp_path):
    args = enroll_args(tmp_path)
    adapter, provider = Enrollment(), Speech()
    assert main(args + ['--check'], enrollment=adapter) == 0
    assert adapter.calls == 0
    assert main(args, enrollment=adapter) == 0
    manifest_path = tmp_path / 'enrolled/manifest.json'
    manifest = load_manifest(manifest_path)
    assert manifest['voices'][0]['reference']['provenance']['kind'] == 'supplied'
    assert manifest['voices'][0]['comparisons'] == []
    passages = tmp_path / 'passages'
    passages.mkdir()
    (passages / '02.txt').write_text('Second passage')
    (passages / '01.txt').write_text('First passage')
    compare = ['compare', '--manifest', str(manifest_path), '--passages', str(passages), '--speeds', '1', '1.1']
    assert main(compare + ['--check'], provider=provider) == 0
    assert not provider.calls
    assert main(compare, provider=provider) == 0
    assert len(provider.calls) == 4
    assert [text for text, _ in provider.calls] == ['First passage', 'Second passage'] * 2
    assert all(options.instructions == '' and options.model == CLONE_MODEL for _, options in provider.calls)
    manifest = load_manifest(manifest_path)
    assert all(track['boundaries'] == [0.0, 3.0] for track in manifest['voices'][0]['comparisons'])
    report = (manifest_path.parent / 'report.html').read_text()
    assert '&lt;Kai Narrator&gt;' in report and '<Kai Narrator>' not in report
    assert '<audio controls' in report and 'aria-label=' in report
    assert 'reference.wav' in report
    assert main(['inspect', '--manifest', str(manifest_path)]) == 0
    assert adapter.calls == 1


def test_uncertain_enrollment_requires_explicit_recovery(tmp_path):
    args = enroll_args(tmp_path)
    adapter = Enrollment(uncertain=True)
    assert main(args, enrollment=adapter) == 1
    path = tmp_path / 'enrolled/manifest.json'
    assert load_manifest(path)['voices'][0]['status'] == 'uncertain'
    assert main(args + ['--resume', str(path)], enrollment=adapter) == 1
    assert adapter.calls == 1
    before = path.read_bytes()
    assert main(['enroll', '--resume', str(path), '--lookup'], enrollment=adapter) == 0
    assert path.read_bytes() == before
    assert main(['enroll', '--resume', str(path), '--adopt-voice-id', 'qwen-tts-vc-example'], enrollment=adapter) == 0
    assert load_manifest(path)['voices'][0]['enrollment']['voice'] == 'qwen-tts-vc-example'
    assert adapter.calls == 1


def test_partial_comparison_has_no_full_track_link(tmp_path):
    assert main(enroll_args(tmp_path), enrollment=Enrollment()) == 0
    text = tmp_path / 'passage.txt'
    text.write_text('Hello')
    path = tmp_path / 'enrolled/manifest.json'
    assert main(['compare', '--manifest', str(path), '--passages', str(text), '--speeds', '1'], provider=Speech(fail_at=1)) == 1
    manifest = load_manifest(path)
    assert 'audio' not in manifest['voices'][0]['comparisons'][0]
    report = (path.parent / 'report.html').read_text()
    assert 'failed' in report and '&lt;private failure&gt;' in report


def test_candidate_provenance_control_and_byte_identity(tmp_path):
    text = tmp_path / 'reference.txt'
    text.write_text('The reference passage.')
    instructions = tmp_path / 'instructions.txt'
    instructions.write_text('A precise custom delivery.')
    samples = tmp_path / 'samples'
    assert main(['candidates', '--text', str(text), '--voices', 'Neil', '--speeds', '1.25', '--instructions', str(instructions), '--output', str(samples)], provider=Speech()) == 0
    args = ['enroll', '--reference', str(samples / '001.wav'), '--candidate-manifest', str(samples / 'manifest.json'), '--sample', '1', '--name', 'Neil Narrator', '--key', 'readvox-neil-v2', '--output', str(tmp_path / 'voice')]
    assert main(args, enrollment=Enrollment()) == 0
    path = tmp_path / 'voice/manifest.json'
    entry = load_manifest(path)['voices'][0]
    assert entry['reference']['provenance']['settings']['instructions'] == 'A precise custom delivery.'
    assert entry['reference']['provenance']['text']['sha256'] == load_manifest(samples / 'manifest.json')['text']['sha256']
    assert (path.parent / entry['reference']['provenance']['text']['path']).read_text() == 'The reference passage.'
    provider = Speech()
    assert main(['compare', '--manifest', str(path), '--passages', str(text), '--speeds', '1', '--control-manifest', str(samples / 'manifest.json'), '--control-sample', '1'], provider=provider) == 0
    assert len(provider.calls) == 2
    control = provider.calls[1][1]
    assert control.voice == 'Neil' and control.speed == 1.25 and control.instructions == 'A precise custom delivery.'


def test_rotated_credential_requires_acknowledgement_before_adoption(tmp_path):
    adapter = Enrollment(uncertain=True)
    assert main(enroll_args(tmp_path), enrollment=adapter) == 1
    path = tmp_path / 'enrolled/manifest.json'
    args = ['enroll', '--resume', str(path), '--adopt-voice-id', 'qwen-tts-vc-example']
    adapter.account_fingerprint = 'new-credential'
    assert main(args, enrollment=adapter) == 1
    assert main(args + ['--acknowledge-credential-change'], enrollment=adapter) == 0
    assert load_manifest(path)['voices'][0]['enrollment']['account_fingerprint'] == 'new-credential'


def test_comparison_resume_does_not_repeat_completed_passages(tmp_path):
    assert main(enroll_args(tmp_path), enrollment=Enrollment()) == 0
    passage_dir = tmp_path / 'texts'
    passage_dir.mkdir()
    (passage_dir / '1.txt').write_text('One')
    (passage_dir / '2.txt').write_text('Two')
    path = tmp_path / 'enrolled/manifest.json'
    provider = Speech(fail_at=2)
    args = ['compare', '--manifest', str(path), '--passages', str(passage_dir), '--speeds', '1']
    assert main(args, provider=provider) == 1
    assert main(args + ['--resume', str(path)], provider=provider) == 0
    assert [text for text, _ in provider.calls] == ['One', 'Two', 'Two']


def test_new_comparison_copies_only_manifest_owned_assets(tmp_path):
    assert main(enroll_args(tmp_path), enrollment=Enrollment()) == 0
    path = tmp_path / 'enrolled/manifest.json'
    (path.parent / 'unrelated-secret.txt').write_text('Do not copy')
    passage = tmp_path / 'passage.txt'
    passage.write_text('A passage')
    output = tmp_path / 'comparison'
    assert main(['compare', '--manifest', str(path), '--passages', str(passage), '--speeds', '1', '--output', str(output)], provider=Speech()) == 0
    assert not (output / 'unrelated-secret.txt').exists()
    assert (output / 'reference.wav').exists()
    assert load_manifest(path)['voices'][0]['comparisons'] == []


def test_interrupted_multi_speed_comparison_has_complete_resume_matrix(tmp_path):
    import asyncio
    assert main(enroll_args(tmp_path), enrollment=Enrollment()) == 0
    passages = tmp_path / 'passages'
    passages.mkdir()
    (passages / '1.txt').write_text('One')
    (passages / '2.txt').write_text('Two')
    path = tmp_path / 'enrolled/manifest.json'
    class InterruptedSpeech(Speech):
        async def stream_speech(self, text, options):
            if len(self.calls) == 1:
                self.calls.append((text, options))
                raise asyncio.CancelledError()
            async for chunk in super().stream_speech(text, options):
                yield chunk
    provider = InterruptedSpeech()
    args = ['compare', '--manifest', str(path), '--passages', str(passages), '--speeds', '1', '1.1', '1.25']
    with pytest.raises(asyncio.CancelledError):
        main(args, provider=provider)
    saved = load_manifest(path)
    assert len(saved['voices'][0]['comparisons']) == 3
    assert all(len(track['passages']) == 2 for track in saved['voices'][0]['comparisons'])
    resumed = Speech()
    assert main(args + ['--resume', str(path)], provider=resumed) == 0
    assert [text for text, _ in resumed.calls] == ['Two', 'One', 'Two', 'One', 'Two']


def test_chinese_candidate_cannot_be_enrolled_as_english(tmp_path):
    text = tmp_path / 'reference.txt'
    text.write_text('Chinese reference candidate.')
    samples = tmp_path / 'samples'
    assert main(['candidates', '--text', str(text), '--voices', 'Kai', '--speeds', '1', '--language', 'zh', '--output', str(samples)], provider=Speech()) == 0
    enrollment = Enrollment()
    output = tmp_path / 'voice'
    args = ['enroll', '--reference', str(samples / '001.wav'), '--candidate-manifest', str(samples / 'manifest.json'), '--sample', '1', '--name', 'Kai', '--key', 'readvox-kai-v2', '--output', str(output)]
    assert main(args + ['--check'], enrollment=enrollment) == 1
    assert main(args, enrollment=enrollment) == 1
    assert enrollment.calls == 0 and not output.exists()


@pytest.mark.parametrize('tamper', ['id', 'voice', 'identity', 'completed', 'status'])
def test_comparison_tampering_rejected_before_writes_or_requests(tmp_path, tamper):
    assert main(enroll_args(tmp_path), enrollment=Enrollment()) == 0
    path = tmp_path / 'enrolled/manifest.json'
    passage = tmp_path / 'passage.txt'
    passage.write_text('A passage')
    args = ['compare', '--manifest', str(path), '--passages', str(passage), '--speeds', '1']
    assert main(args, provider=Speech(fail_at=1)) == 1
    manifest = json.loads(path.read_text())
    track = manifest['voices'][0]['comparisons'][0]
    if tamper == 'id': track['id'] = '../outside'
    if tamper == 'voice': track['settings']['voice'] = 'qwen-tts-vc-other'
    if tamper == 'identity': track['input_identity']['settings']['speed'] = 1.1
    if tamper == 'completed': track['status'] = 'completed'
    if tamper == 'status': track['passages'][0]['status'] = 'unexpected'
    path.write_text(json.dumps(manifest))
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    provider = Speech()
    assert main(args + ['--resume', str(path), '--check'], provider=provider) == 1
    assert main(args + ['--resume', str(path)], provider=provider) == 1
    assert provider.calls == []
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before


def test_generated_audio_symlink_escape_rejected_before_calls(tmp_path):
    assert main(enroll_args(tmp_path), enrollment=Enrollment()) == 0
    path = tmp_path / 'enrolled/manifest.json'
    passage = tmp_path / 'passage.txt'
    passage.write_text('A passage')
    args = ['compare', '--manifest', str(path), '--passages', str(passage), '--speeds', '1']
    assert main(args, provider=Speech(fail_at=1)) == 1
    track_id = load_manifest(path)['voices'][0]['comparisons'][0]['id']
    outside = tmp_path / 'outside.wav'
    outside.write_bytes(b'Original bytes')
    (path.parent / f'{track_id}-1.wav').symlink_to(outside)
    before = path.read_bytes()
    provider = Speech()
    assert main(args + ['--resume', str(path), '--check'], provider=provider) == 1
    assert main(args + ['--resume', str(path)], provider=provider) == 1
    assert not provider.calls
    assert path.read_bytes() == before and outside.read_bytes() == b'Original bytes'


def test_retired_import_command_rejects_without_creating_artifacts(tmp_path):
    output = tmp_path / 'imported'
    with pytest.raises(SystemExit) as error:
        main(['import-legacy', '--manifest', str(tmp_path / 'missing.json'), '--output', str(output)])
    assert error.value.code == 2
    assert not output.exists()

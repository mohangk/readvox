"""Offline conversion of documented root-relative comparison artifacts."""
import copy
import json
from pathlib import Path
import shutil

from tts_app.providers.qwen_enrollment import CLONE_MODEL, validate_reference
from tts_app.voice_tools.audio import sha256
from tts_app.voice_tools.approved import APPROVED_RUN, is_approved_legacy
from tts_app.voice_tools.common import new_run, text_hash, timestamp
from tts_app.voice_tools.manifest import save_manifest, validate_manifest
from tts_app.voice_tools.report import write_report

SELECTIONS = {16: ('Kai', 1.0), 11: ('Vivian', 1.1), 6: ('Bellona', 1.25), 1: ('Neil', 1.0)}


def import_legacy_comparison(source: Path, output: Path, *, check=False) -> Path:
    if output.exists():
        raise ValueError('Choose a new output directory')
    original = json.loads(source.read_text(encoding='utf-8'))
    run_id = original['run_id']
    if '/' in run_id or '\\' in run_id or run_id in {'.', '..'}:
        raise ValueError('Invalid legacy run identity')
    # publish() stored paths relative to clone-lab-data, while its manifest was in the run child.
    root = source.resolve().parent.parent if source.resolve().parent.name == run_id else source.resolve().parent
    run_root = (root / run_id).resolve()
    copies, texts = {}, {}
    def copied(relative):
        relative_path = Path(relative)
        origin = (root / relative_path).resolve()
        if relative_path.is_absolute() or not origin.is_relative_to(run_root) or not origin.is_file():
            raise ValueError('Legacy asset escapes its run root or is missing')
        destination = 'assets/' + origin.relative_to(run_root).as_posix()
        copies[destination] = origin
        return {'path': destination, 'sha256': sha256(origin)}
    def text_asset(name, text):
        texts[name] = text
        return {'path': name, 'sha256': text_hash(text)}
    reference_text = text_asset('reference.txt', original['reference_text'])
    passage_texts = [text_asset(f'passage-{i + 1}.txt', p['text']) for i, p in enumerate(original['passages'])]
    manifest = {'schema_version': 1, 'kind': 'voice', 'run_id': output.name, 'legacy_run_id': run_id, 'voices': []}
    numbers = {v['number'] for v in original['voices']}
    historical_run = (numbers == set(SELECTIONS) and len(original['voices']) == 4
                      and is_approved_legacy(source, original))
    for old in original['voices']:
        source_settings = copy.deepcopy(original['settings']) | {'voice': old['voice'], 'speed': old['speed']}
        reference = copied(old['reference_audio'])
        validate_reference(copies[reference['path']])
        reference['provenance'] = {'kind': 'legacy-candidate', 'run_id': run_id, 'gallery_run_id': original.get('gallery_run_id'),
                                   'sample_number': old['number'], 'settings': source_settings, 'text': reference_text}
        enrollment = copy.deepcopy(old.get('enrollment'))
        if enrollment:
            enrollment['preferred_name'] = old.get('preferred_name')
            enrollment['endpoint_region'] = 'dashscope-intl.aliyuncs.com' if historical_run else None
            enrollment['account_fingerprint'] = None  # Historical credentials were not recorded.
        source_name = old['voice']
        key = f'readvox-{source_name.lower()}-v1'
        entry = {'key': key, 'name': source_name + ' Narrator', 'language': {'English': 'en', 'Chinese': 'zh'}[source_settings['language']],
                 'speed': old['speed'], 'target_model': original['clone_model'], 'reference': reference, 'enrollment': enrollment,
                 'preferred_name': old.get('preferred_name'), 'status': old['status'], 'comparisons': [], 'acceptance': None}
        for mode, old_track in old.get('tracks', {}).items():
            config = source_settings | {k: old_track[k] for k in ('model', 'speed', 'instructions') if k in old_track}
            if mode == 'cloned':
                if not enrollment:
                    raise ValueError('Cloned comparison is missing its enrollment')
                if old_track.get('model') != enrollment['target_model'] or old_track.get('instructions') != '':
                    raise ValueError('Cloned legacy track settings disagree with enrollment')
                config |= {'voice': enrollment['voice']}
            track = {'id': f'legacy-{old["number"]}-{mode}', 'mode': mode, 'settings': config, 'status': old_track['status'], 'passages': []}
            if len(old_track.get('segments', [])) > len(passage_texts):
                raise ValueError('Legacy passage metadata differs from segments')
            for i, passage_text in enumerate(passage_texts):
                segments = old_track.get('segments', [])
                passage = {'text': passage_text, 'status': 'queued', 'source_segment_indexes': original['passages'][i].get('source_segment_indexes', [])}
                if i < len(segments):
                    passage |= {'audio': copied(segments[i]['audio']), 'duration': segments[i]['duration'], 'status': 'completed'}
                track['passages'].append(passage)
            if old_track.get('audio'):
                track['audio'] = copied(old_track['audio'])
            for field in ('duration', 'boundaries', 'error'):
                if field in old_track:
                    track[field] = copy.deepcopy(old_track[field])
            if track['status'] == 'completed' and ('audio' not in track or any(p['status'] != 'completed' for p in track['passages'])):
                raise ValueError('Completed legacy comparison has incomplete audio')
            track['input_identity'] = {'mode': mode, 'settings': config, 'passage_hashes': [p['text']['sha256'] for p in track['passages']]}
            entry['comparisons'].append(track)
        selection = SELECTIONS.get(old['number'])
        cloned = next((t for t in entry['comparisons'] if t['mode'] == 'cloned'), None)
        if (historical_run and selection == (old['voice'], old['speed']) and old['status'] == 'completed'
                and enrollment and enrollment['target_model'] == CLONE_MODEL and cloned
                and cloned['status'] == 'completed' and cloned['settings']['speed'] == old['speed']
                and all(t['status'] == 'completed' for t in entry['comparisons'])):
            entry['acceptance'] = {'key': key, 'speed': old['speed'], 'accepted_at': None,
                                   'recorded_at': timestamp(), 'source': 'historical-selection', 'legacy_run_id': run_id}
        manifest['voices'].append(entry)
    path = output / 'manifest.json'
    validate_manifest(manifest, path, verify_assets=False)
    if check:
        return path
    manifest.update(new_run(output, 'voice'))
    for relative, origin in copies.items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, destination)
    for relative, content in texts.items():
        (output / relative).write_text(content, encoding='utf-8')
    save_manifest(path, manifest)
    write_report(output / 'report.html', manifest)
    return path

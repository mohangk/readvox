"""Independent passage requests using existing enrollment, never implicit create."""
import copy
from dataclasses import asdict
from pathlib import Path
import shutil
from uuid import uuid4

from tts_app.providers.base import TTSOptions
from tts_app.voice_tools.audio import asset, read_pcm, write_track
from tts_app.voice_tools.common import read_text, synthesize, text_hash
from tts_app.voice_tools.enroll import selected_candidate
from tts_app.voice_tools.manifest import load_manifest, resolve_asset, save_manifest, validate_speed
from tts_app.voice_tools.report import write_report


async def run(args, *, provider):
    path = args.manifest or args.resume
    if path is None:
        raise ValueError('Comparison requires --manifest or --resume')
    if args.resume and args.resume.resolve() != path.resolve():
        raise ValueError('Resume manifest differs')
    manifest = load_manifest(path)
    if manifest['kind'] != 'voice':
        raise ValueError('Comparison requires a voice manifest')
    files = sorted(args.passages.glob('*.txt')) if args.passages.is_dir() else [args.passages]
    if not files:
        raise ValueError('Supply one or more UTF-8 .txt passages')
    texts = [read_text(file) for file in files]
    for speed in args.speeds:
        validate_speed(speed)
    if len(set(args.speeds)) != len(args.speeds):
        raise ValueError('Speeds must be unique')
    control = None
    if args.control_manifest:
        _, sample = selected_candidate(args.control_manifest, args.control_sample)
        control = copy.deepcopy(sample['settings'])
    elif args.control_sample is not None:
        raise ValueError('--control-sample requires --control-manifest')
    configurations = []
    for entry in manifest['voices']:
        enrollment = entry.get('enrollment')
        if not enrollment:
            raise ValueError('Comparison requires a saved enrollment for every voice')
        for speed in args.speeds:
            options = asdict(TTSOptions(voice=enrollment['voice'], model=enrollment['target_model'], speed=speed,
                                      language={'en': 'English', 'zh': 'Chinese'}[entry['language']], instructions='', audio_format='pcm'))
            configurations.append((entry, 'cloned', options))
        if control:
            configurations.append((entry, 'original', control))
    identities = [{'mode': mode, 'settings': config, 'passage_hashes': [text_hash(text) for text in texts]} for _, mode, config in configurations]
    selected = []
    for (entry, mode, config), identity in zip(configurations, identities):
        track = next((track for track in entry['comparisons'] if track.get('input_identity') == identity), None)
        if args.resume and track is None:
            raise ValueError('Resume comparison inputs differ from existing tracks')
        if track and not args.resume:
            raise ValueError('Comparison already exists; use explicit --resume')
        selected.append((entry, track, identity))
    # Validate every future destination before check mode or any manifest updates.
    destination_manifest = args.output / 'manifest.json' if args.output else path
    for _, track, _ in selected:
        if track is not None:
            for index in range(len(track['passages'])):
                resolve_asset(destination_manifest, f'{track["id"]}-{index + 1}.wav')
            resolve_asset(destination_manifest, f'{track["id"]}-full.wav')
    if args.output and args.output.exists():
        raise ValueError('Comparison output must be a new directory')
    count = sum(len(texts) if track is None else sum(p['status'] != 'completed' for p in track['passages']) for _, track, _ in selected)
    print(f'{count} TTS requests; 0 enrollments')
    if args.check:
        return 0
    if args.output:
        # New comparison runs own exact copies, including their original references.
        args.output.mkdir(parents=True, exist_ok=False)
        def copy_assets(value):
            if isinstance(value, dict):
                if 'path' in value:
                    origin = resolve_asset(path, value['path'])
                    destination = resolve_asset(args.output / 'manifest.json', value['path'])
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(origin, destination)
                for child in value.values():
                    copy_assets(child)
            elif isinstance(value, list):
                for child in value:
                    copy_assets(child)
        copy_assets(manifest)
        path = args.output / 'manifest.json'
        manifest['run_id'] = args.output.name + '-' + uuid4().hex[:8]
    prepared = []
    for entry, track, identity in selected:
        if track is None:
            track_id = uuid4().hex[:12]
            passage_records = []
            for index, text in enumerate(texts):
                text_path = resolve_asset(path, f'{track_id}-{index + 1}.txt')
                text_path.write_text(text, encoding='utf-8')
                passage_records.append({'text': asset(text_path, path.parent), 'status': 'queued'})
            track = {'id': track_id, 'mode': identity['mode'], 'settings': identity['settings'],
                     'input_identity': identity, 'passages': passage_records, 'status': 'queued'}
            entry['comparisons'].append(track)
        prepared.append(track)
    # Persist the complete matrix before the first external synthesis request.
    save_manifest(path, manifest)
    write_report(path.parent / 'report.html', manifest)
    for track in prepared:
        if track['status'] == 'completed':
            continue
        track.update(status='generating')
        track.pop('error', None)
        save_manifest(path, manifest)
        try:
            for index, passage in enumerate(track['passages']):
                if passage['status'] == 'completed':
                    continue
                passage.update(status='generating')
                save_manifest(path, manifest)
                audio, duration = await synthesize(provider, texts[index], track['settings'], resolve_asset(path, f'{track["id"]}-{index + 1}.wav'))
                passage.update(status='completed', audio=audio, duration=duration)
                save_manifest(path, manifest)
            chunks = [read_pcm(resolve_asset(path, passage['audio']['path'])) for passage in track['passages']]
            full_path = resolve_asset(path, f'{track["id"]}-full.wav')
            boundaries = write_track(full_path, chunks, track['settings']['sample_rate'])
            track.update(status='completed', audio=asset(full_path, path.parent), boundaries=boundaries,
                         duration=sum(p['duration'] for p in track['passages']))
        except (RuntimeError, TimeoutError, ValueError) as error:
            track.update(status='failed', error=str(error) or type(error).__name__)
            for passage in track['passages']:
                if passage['status'] == 'generating':
                    passage['status'] = 'failed'
        save_manifest(path, manifest)
        write_report(path.parent / 'report.html', manifest)
    return int(any(t['status'] != 'completed' for e in manifest['voices'] for t in e['comparisons']))

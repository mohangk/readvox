"""Independent reference text to an explicitly configured candidate matrix."""
from pathlib import Path

from tts_app.profile_defaults import AUDIOBOOK_INSTRUCTIONS
from tts_app.voice_tools.audio import asset
from tts_app.voice_tools.common import new_run, read_text, settings, synthesize, text_hash
from tts_app.voice_tools.manifest import load_manifest, save_manifest
from tts_app.voice_tools.report import write_report


async def run(args, *, provider):
    text = read_text(args.text)
    instructions = args.instructions.read_text(encoding='utf-8') if args.instructions else AUDIOBOOK_INSTRUCTIONS
    matrix = [settings(voice=voice, speed=speed, model=args.model, language=args.language, instructions=instructions)
              for voice in args.voices for speed in args.speeds]
    if len({(s['voice'], s['speed']) for s in matrix}) != len(matrix):
        raise ValueError('Candidate voices and speeds must be unique')
    identity = {'text_sha256': text_hash(text), 'settings': matrix}
    if args.resume:
        path = args.resume
        manifest = load_manifest(path)
        if manifest['kind'] != 'candidates' or manifest.get('input_identity') != identity:
            raise ValueError('Resume input identity differs from saved candidate run')
        if args.output and args.output.resolve() != path.resolve().parent:
            raise ValueError('Resume output does not match manifest')
    else:
        if not args.output or args.output.exists():
            raise ValueError('Choose a new output directory or explicit --resume')
        path = args.output / 'manifest.json'
        manifest = None
    count = len(matrix) if manifest is None else sum(s['status'] != 'completed' for s in manifest['samples'])
    print(f'{count} TTS requests; 0 enrollments')
    if args.check:
        return 0
    if manifest is None:
        manifest = new_run(path.parent, 'candidates') | {'input_identity': identity, 'samples': []}
        text_path = path.parent / 'reference.txt'
        text_path.write_text(text, encoding='utf-8')
        manifest['text'] = asset(text_path, path.parent)
        manifest['samples'] = [{'number': i + 1, 'settings': config, 'text_sha256': text_hash(text), 'status': 'queued'} for i, config in enumerate(matrix)]
        save_manifest(path, manifest)
    for sample in manifest['samples']:
        if sample['status'] == 'completed':
            continue
        sample.update(status='generating')
        sample.pop('error', None)
        save_manifest(path, manifest)
        try:
            audio, duration = await synthesize(provider, text, sample['settings'], path.parent / f'{sample["number"]:03}.wav')
            sample.update(status='completed', audio=audio, duration=duration)
        except (RuntimeError, TimeoutError, ValueError) as error:
            sample.update(status='failed', error=str(error) or type(error).__name__)
        save_manifest(path, manifest)
        write_report(path.parent / 'report.html', manifest)
    return int(any(s['status'] != 'completed' for s in manifest['samples']))

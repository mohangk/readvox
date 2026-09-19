"""Maintained operator command line; paid operations are always explicit."""
import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from tts_app.config import load_settings
from tts_app.providers.qwen import QwenTTSProvider
from tts_app.providers.qwen_enrollment import QwenEnrollment
from tts_app.voice_tools import candidates, compare, enroll
from tts_app.voice_tools.manifest import load_manifest


def parser():
    root = argparse.ArgumentParser(description='Readvox private voice workshop. Enrollment and synthesis commands are paid; --check is offline.')
    commands = root.add_subparsers(dest='command', required=True)
    candidate = commands.add_parser('candidates', help='Generate reference candidates')
    candidate.add_argument('--text', type=Path, required=True)
    candidate.add_argument('--voices', nargs='+', required=True)
    candidate.add_argument('--speeds', nargs='+', type=float, required=True)
    candidate.add_argument('--model', default='qwen3-tts-instruct-flash-realtime')
    candidate.add_argument('--language', default='en')
    candidate.add_argument('--instructions', type=Path, help='UTF-8 instructions file; defaults to audiobook instructions')
    candidate.add_argument('--output', type=Path)
    candidate.add_argument('--resume', type=Path)
    candidate.add_argument('--check', action='store_true')
    enrollment = commands.add_parser('enroll', help='Explicitly enroll one WAV, or recover an interrupted create')
    for name in ('reference', 'output', 'resume', 'candidate-manifest'):
        enrollment.add_argument('--' + name, type=Path)
    for name in ('name', 'key', 'model', 'adopt-voice-id'):
        enrollment.add_argument('--' + name)
    enrollment.add_argument('--speed', type=float)
    enrollment.add_argument('--sample', type=int)
    enrollment.add_argument('--lookup', action='store_true')
    enrollment.add_argument('--page-index', type=int, default=0)
    enrollment.add_argument('--acknowledge-credential-change', action='store_true', help='Confirm the rotated credential belongs to the same provider account')
    enrollment.add_argument('--check', action='store_true')
    comparison = commands.add_parser('compare', help='Compare separate passage requests using saved enrollment')
    for name in ('manifest', 'resume', 'output', 'control-manifest'):
        comparison.add_argument('--' + name, type=Path)
    comparison.add_argument('--passages', type=Path, required=True, help='One UTF-8 text file or directory of ordered .txt files')
    comparison.add_argument('--speeds', nargs='+', type=float, required=True)
    comparison.add_argument('--control-sample', type=int)
    comparison.add_argument('--check', action='store_true')
    inspect = commands.add_parser('inspect', help='Inspect local verified artifacts without cloud lookup')
    inspect.add_argument('--manifest', type=Path, required=True)
    installation = commands.add_parser('install', help='Install approved voices into SQLite and durable reference storage, offline')
    installation.add_argument('--manifest', type=Path, required=True)
    installation.add_argument('--accept', nargs='+', help='Explicitly accept selected stable voice keys')
    installation.add_argument('--speed', type=float, help='Choose a tested synthesis speed')
    installation.add_argument('--check', action='store_true')
    return root


async def dispatch(args, *, provider=None, enrollment=None):
    if args.command == 'install':
        from tts_app.voice_catalog_install import install_clone_manifest
        from tts_app.voice_tools.common import timestamp
        from tts_app.voice_tools.manifest import save_manifest
        settings = load_settings()
        install_clone_manifest(args.manifest, settings=settings, check_only=True,
                               accepted_keys=args.accept, speed=args.speed)
        if not args.check and args.accept:
            data = json.loads(args.manifest.read_text())
            changed = False
            for voice in data['voices']:
                if voice['key'] in args.accept:
                    previous = voice.get('acceptance') or {}
                    speed = args.speed if args.speed is not None else previous.get('speed', voice['speed'])
                    if previous.get('key') != voice['key'] or previous.get('speed') != speed:
                        voice['acceptance'] = {'key': voice['key'], 'speed': speed,
                                               'accepted_at': timestamp(), 'source': 'operator'}
                        changed = True
            if changed:
                save_manifest(args.manifest, data)
        installed = install_clone_manifest(args.manifest, settings=settings, check_only=args.check,
                                           accepted_keys=args.accept, speed=args.speed)
        print(json.dumps([{'name': profile['name'], 'key': profile['key']}
                          for profile in installed], indent=2))
        return 0
    if args.command == 'inspect':
        data = load_manifest(args.manifest)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    settings = load_settings()
    if args.command == 'enroll':
        if args.lookup and args.adopt_voice_id:
            raise ValueError('Choose lookup or adoption, separately')
        if enrollment is not None:
            return await enroll.run(args, enrollment=enrollment)
        host = urlsplit(settings.qwen_realtime_url).hostname
        async with httpx.AsyncClient(timeout=120) as client:
            adapter = QwenEnrollment(settings.qwen_api_key, f'https://{host}/api/v1/services/audio/tts/customization', client=client, target_model=args.model or 'qwen3-tts-vc-realtime-2026-01-15')
            return await enroll.run(args, enrollment=adapter)
    if provider is None:
        provider = QwenTTSProvider(settings.qwen_api_key, settings.qwen_model, settings.qwen_realtime_url)
    return await {'candidates': candidates.run, 'compare': compare.run}[args.command](args, provider=provider)


def main(argv: list[str] | None = None, *, provider=None, enrollment=None) -> int:
    args = parser().parse_args(argv)
    try:
        return asyncio.run(dispatch(args, provider=provider, enrollment=enrollment))
    except (ValueError, OSError, RuntimeError) as error:
        print(f'Error: {error}')
        return 1

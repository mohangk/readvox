"""Offline promotion of approved enrollments into SQLite and durable reference assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
from uuid import uuid4

from tts_app.config import load_settings
from tts_app.providers.registry import get_provider
from tts_app.providers.qwen_enrollment import CLONE_MODEL, validate_reference, validate_voice_id
from tts_app.voice_installation import preflight_voice_installations, installation_voice
from tts_app.storage import Storage
from tts_app.synthesis import SAMPLE_TEXT
from tts_app.voice_tools.manifest import load_manifest, resolve_asset
from tts_app.voice_tools.approved import APPROVED_RUN, is_approved_legacy

logger = logging.getLogger(__name__)
APPROVED = {16: ('Kai', 1.0), 11: ('Vivian', 1.1), 6: ('Bellona', 1.25), 1: ('Neil', 1.0)}


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _legacy_entries(source, manifest):
    if manifest.get('run_id') != APPROVED_RUN or manifest.get('clone_model') != CLONE_MODEL:
        raise ValueError('Use import-legacy and explicit acceptance for a new comparison run')
    if not is_approved_legacy(source, manifest):
        raise ValueError('Historical approval does not match these manifest/reference bytes; import-legacy and explicitly accept after listening')
    voices = manifest.get('voices', [])
    if len(voices) != 4 or {v.get('number') for v in voices} != set(APPROVED):
        raise ValueError('The approved run must contain exactly the four selected voices')
    root = source.resolve().parent
    if root.name == APPROVED_RUN:
        root = root.parent
    entries = []
    for old in voices:
        name, speed = APPROVED[old['number']]
        track = old.get('tracks', {}).get('cloned', {})
        enrollment = old.get('enrollment', {})
        if (old.get('voice') != name or old.get('speed') != speed or old.get('status') != 'completed'
                or track.get('status') != 'completed' or track.get('model') != CLONE_MODEL
                or track.get('speed') != speed or track.get('instructions') != ''):
            raise ValueError('Approved clone settings or completion do not match the selected sample')
        reference = (root / old['reference_audio']).resolve()
        if Path(old['reference_audio']).is_absolute() or not reference.is_relative_to((root / APPROVED_RUN).resolve()):
            raise ValueError('Reference escapes the approved run')
        entries.append(dict(key=f'readvox-{name.lower()}-v1', name=f'{name} Narrator', language='en', speed=speed,
                            enrollment=enrollment, reference=reference, preview_text=manifest['reference_text'],
                            provenance={'source_run_id': APPROVED_RUN, 'selection': old['number'],
                                        'reference_settings': {**manifest['settings'], 'voice': name, 'speed': speed},
                                        'preferred_name': old.get('preferred_name'), 'enrollment': enrollment,
                                        'acceptance': 'historical-selection'}))
    return entries


def _versioned_entries(source, manifest, accepted_keys, speed):
    entries = []
    available = {voice['key'] for voice in manifest['voices']}
    if accepted_keys and not set(accepted_keys) <= available:
        raise ValueError('Unknown voice acceptance key')
    for voice in manifest['voices']:
        explicit = voice['key'] in (accepted_keys or [])
        if accepted_keys and not explicit:
            continue
        acceptance = voice.get('acceptance') or {}
        if not explicit and acceptance.get('key') != voice['key']:
            raise ValueError('Explicit --accept is required for an unelected voice')
        chosen_speed = speed if explicit and speed is not None else acceptance.get('speed', voice['speed'])
        enrollment = voice.get('enrollment') or {}
        completed = [track for track in voice['comparisons'] if track.get('mode') == 'cloned'
                     and track.get('status') == 'completed' and track.get('settings', {}).get('speed') == chosen_speed]
        def matches(track):
            settings = track['settings']
            return (settings.get('voice') == enrollment.get('voice') and settings.get('model') == enrollment.get('target_model')
                    and settings.get('instructions') == '' and settings.get('language') == 'English'
                    and track.get('audio') and track.get('passages')
                    and all(p.get('status') == 'completed' and p.get('audio') for p in track['passages']))
        if not any(matches(track) for track in completed):
            raise ValueError('Accept a speed with a completed matching cloned-voice comparison')
        provenance = dict(voice['reference']['provenance'])
        text = provenance.get('text')
        preview = resolve_asset(source, text['path']).read_text(encoding='utf-8') if isinstance(text, dict) else SAMPLE_TEXT['en']
        entries.append(dict(key=voice['key'], name=voice['name'], language=voice['language'], speed=chosen_speed,
                            enrollment=enrollment, reference=resolve_asset(source, voice['reference']['path']), preview_text=preview,
                            provenance={'source_run_id': manifest['run_id'], 'reference': provenance, 'enrollment': enrollment,
                                        'acceptance': acceptance if acceptance.get('key') == voice['key'] and acceptance.get('speed') == chosen_speed
                                        else {'key': voice['key'], 'speed': chosen_speed, 'source': 'operator'}}))
    if not entries:
        raise ValueError('No approved voices to install')
    return entries


def install_clone_manifest(manifest_path: Path, *, settings, storage=None, check_only=False, accepted_keys=None, speed=None):
    get_provider(settings)  # Validate runtime configuration before any migration or write.
    # This Qwen enrollment installer owns the legacy migration context in both
    # preflight (through its definitions) and apply, independently of runtime.
    installation_provider = 'qwen'
    source = Path(manifest_path)
    source_bytes = source.read_bytes()
    manifest = json.loads(source_bytes)
    if not isinstance(manifest, dict):
        raise ValueError('Voice manifest must be an object')
    if 'schema_version' in manifest:
        manifest = load_manifest(source)
        if manifest['kind'] != 'voice':
            raise ValueError('Install requires an enrolled-voice manifest')
        references = {voice['key']: resolve_asset(source, voice['reference']['path']) for voice in manifest['voices']}
        entries = _versioned_entries(source, manifest, accepted_keys, speed)
    else:
        entries = _legacy_entries(source, manifest)
        references = {entry['key']: entry['reference'] for entry in entries}
        if accepted_keys:
            entries = [entry for entry in entries if entry['key'] in accepted_keys]
            if len(entries) != len(set(accepted_keys)):
                raise ValueError('Unknown approved voice key')
        if speed is not None and any(entry['speed'] != speed for entry in entries):
            raise ValueError('Historical installation preserves the approved speeds')
    digest = _hash(source_bytes)
    # Preserve the complete reference set so later selections can reuse this bundle.
    assets = {key + '.wav': path.read_bytes() for key, path in references.items()}
    definitions = []
    for entry in entries:
        enrollment = entry['enrollment']
        validate_voice_id(enrollment.get('voice'))
        if enrollment.get('target_model') != CLONE_MODEL or enrollment.get('fallback_mode'):
            raise ValueError('Enrollment model or reported fallback requires review')
        validate_reference(entry['reference'])
        content = entry['reference'].read_bytes()
        filename = entry['key'] + '.wav'
        assets[filename] = content
        definitions.append(dict(key=entry['key'], provider=installation_provider, model=CLONE_MODEL,
                                voice=enrollment['voice'], language=entry['language'], name=entry['name'],
                                speed=entry['speed'], instructions='', preview_text=entry['preview_text'],
                                reference_path=f'voices/{digest}/{filename}', reference_sha256=_hash(content),
                                provenance={**entry['provenance'], 'source_manifest_sha256': digest}))
    definitions = preflight_voice_installations(settings.db_path, definitions, reuse_unchanged_source=True)
    base = settings.data_dir / 'voices'
    destination = base / digest
    if not base.resolve().is_relative_to(settings.data_dir.resolve()) or not destination.resolve().is_relative_to(base.resolve()):
        raise ValueError('Installed reference directory escapes the data directory')
    for definition in definitions:
        expected = f"voices/{digest}/{definition['key']}.wav"
        if definition['reference_path'] == expected:
            continue
        # Reused registrations retain their first archive. Verify those bytes too.
        reference = settings.data_dir / definition['reference_path']
        archived_source = reference.parent / 'source.json'
        for target, checksum in [(reference, definition['reference_sha256']),
                                 (archived_source, definition['provenance']['source_manifest_sha256'])]:
            if (not target.resolve().is_relative_to(base.resolve()) or not target.is_file()
                    or _hash(target.read_bytes()) != checksum):
                raise ValueError('Original installed voice bundle is missing or differs; restore its saved assets')
    assets['source.json'] = source_bytes
    if destination.exists():
        for name, content in assets.items():
            target = destination / name
            if not target.resolve().is_relative_to(destination.resolve()) or not target.is_file() or target.read_bytes() != content:
                raise ValueError('Existing reference bundle differs; refusing to overwrite it')
    if check_only:
        return [installation_voice(value) for value in definitions]
    if not destination.exists():
        base.mkdir(parents=True, exist_ok=True)
        staging = base / ('.stage-' + uuid4().hex)
        staging.mkdir()
        for name, content in assets.items():
            (staging / name).write_bytes(content)
        try:
            staging.rename(destination)
        except OSError:
            # Preserve staging for explicit recovery; never replace an existing bundle.
            logger.error('voice_bundle_publish_failed staging=%s', staging)
            raise
    try:
        active_storage = storage or Storage(settings.db_path)
        active_storage.init_schema(provider_name=installation_provider)
        return active_storage.install_voices([installation_voice(value) for value in definitions])
    except Exception:
        logger.error('voice_registration_failed retained_bundle=%s', destination)
        raise


def main():
    parser = argparse.ArgumentParser(description='Install approved cloned voices offline')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--accept', nargs='+')
    parser.add_argument('--speed', type=float)
    args = parser.parse_args()
    try:
        profiles = install_clone_manifest(args.manifest, settings=load_settings(), check_only=args.check,
                                          accepted_keys=args.accept, speed=args.speed)
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')
    print(json.dumps([{'name': p['name'], 'key': p['key']} for p in profiles], indent=2))


if __name__ == '__main__':
    main()

"""Offline promotion of approved enrollments into SQLite and durable reference assets."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from uuid import uuid4

from tts_app.providers.registry import get_provider
from tts_app.providers.qwen_enrollment import CLONE_MODEL, validate_reference, validate_voice_id
from tts_app.voice_installation import preflight_voice_installations, installation_voice
from tts_app.storage import Storage
from tts_app.synthesis import SAMPLE_TEXT
from tts_app.voice_tools.manifest import load_manifest, resolve_asset

logger = logging.getLogger(__name__)


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _accepted_entries(source, manifest, accepted_keys, speed):
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
    get_provider(settings)  # Validate runtime configuration before any write.
    source = Path(manifest_path)
    source_bytes = source.read_bytes()
    manifest = json.loads(source_bytes)
    if not isinstance(manifest, dict):
        raise ValueError('Voice manifest must be an object')
    manifest = load_manifest(source)
    if manifest['kind'] != 'voice':
        raise ValueError('Install requires an enrolled-voice manifest')
    references = {voice['key']: resolve_asset(source, voice['reference']['path']) for voice in manifest['voices']}
    entries = _accepted_entries(source, manifest, accepted_keys, speed)
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
        definitions.append(dict(key=entry['key'], provider='qwen', model=CLONE_MODEL,
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
        active_storage.init_schema()
        return active_storage.install_voices([installation_voice(value) for value in definitions])
    except Exception:
        logger.error('voice_registration_failed retained_bundle=%s', destination)
        raise

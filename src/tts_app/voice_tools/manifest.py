"""Versioned, rooted manifests with verified assets and atomic replacement."""
import json
import math
import os
from pathlib import Path
import re
import tempfile

from tts_app.voice_tools.audio import sha256
from tts_app.providers.options import QWEN_INSTRUCTION_SAMPLE_CAPABILITIES

SCHEMA_VERSION = 1
from tts_app.providers.qwen_enrollment import CLONE_MODEL, validate_voice_id


def resolve_asset(manifest_path: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path or ':' in relative_path or '\\' in relative_path or Path(relative_path).is_absolute():
        raise ValueError('Asset must use a relative path')
    root = manifest_path.resolve().parent
    result = (root / relative_path).resolve()
    if not result.is_relative_to(root):
        raise ValueError('Asset path escapes manifest root')
    return result


def validate_speed(speed):
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or not 0.5 <= speed <= 2:
        raise ValueError('Speed must be between 0.5 and 2')


def _asset_record(value):
    if not isinstance(value, dict) or not isinstance(value.get('path'), str) or not isinstance(value.get('sha256'), str):
        raise ValueError('Comparison text and audio require asset records')


def _duration(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('Comparison duration must be positive and finite')


def _validate_comparisons(entry, path, source_settings, ids):
    statuses = {'queued', 'generating', 'completed', 'failed'}
    for track in entry['comparisons']:
        if not isinstance(track, dict):
            raise ValueError('Comparison must be an object')
        track_id = track.get('id')
        if not isinstance(track_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', track_id) or track_id in ids:
            raise ValueError('Comparison ID must be a unique safe filename component')
        ids.add(track_id)
        if track.get('status') not in statuses or track.get('mode') not in {'original', 'cloned'}:
            raise ValueError('Invalid comparison status or mode')
        config = track.get('settings')
        required = {'voice', 'model', 'speed', 'language', 'instructions', 'audio_format', 'sample_rate'}
        if not isinstance(config, dict) or not required <= config.keys() or config.keys() - (required | {'pitch', 'volume'}):
            raise ValueError('Comparison requires complete synthesis settings')
        validate_speed(config['speed'])
        if (config['language'] not in {'English', 'Chinese'} or config['audio_format'] != 'pcm'
                or config['sample_rate'] != 24000 or config.get('pitch', 1) != 1 or config.get('volume', 1) != 1):
            raise ValueError('Unsupported comparison audio settings')
        if track['mode'] == 'original':
            source_settings(config)
        else:
            enrollment = entry.get('enrollment') or {}
            if (config['voice'] != enrollment.get('voice') or config['model'] != enrollment.get('target_model')
                    or config['instructions'] != '' or config['language'] != {'en': 'English', 'zh': 'Chinese'}[entry['language']]):
                raise ValueError('Cloned comparison settings disagree with enrollment')
        passages = track.get('passages')
        if not isinstance(passages, list) or not passages:
            raise ValueError('Comparison requires evaluation passages')
        hashes = []
        for passage in passages:
            if not isinstance(passage, dict) or passage.get('status') not in statuses:
                raise ValueError('Invalid comparison passage status')
            _asset_record(passage.get('text'))
            hashes.append(passage['text']['sha256'])
            if passage['status'] == 'completed':
                _asset_record(passage.get('audio'))
                _duration(passage.get('duration'))
            elif 'audio' in passage or 'duration' in passage:
                raise ValueError('Incomplete passage cannot claim completed audio')
        identity = {'mode': track['mode'], 'settings': config, 'passage_hashes': hashes}
        if track.get('input_identity') != identity:
            raise ValueError('Comparison settings or passage identity differs')
        if track['status'] == 'completed':
            if any(p['status'] != 'completed' for p in passages):
                raise ValueError('Completed comparison contains incomplete passages')
            _asset_record(track.get('audio'))
            _duration(track.get('duration'))
            boundaries = track.get('boundaries')
            if not isinstance(boundaries, list) or len(boundaries) != len(passages):
                raise ValueError('Completed comparison requires measured passage boundaries')
            elapsed = 0
            for boundary, passage in zip(boundaries, passages):
                if (isinstance(boundary, bool) or not isinstance(boundary, (int, float))
                        or not math.isfinite(boundary) or not math.isclose(boundary, elapsed, abs_tol=1e-6)):
                    raise ValueError('Comparison boundaries disagree with passage durations')
                elapsed += passage['duration']
            if not math.isclose(track['duration'], elapsed, abs_tol=1e-6):
                raise ValueError('Comparison duration disagrees with passage durations')
        elif 'audio' in track or 'duration' in track or 'boundaries' in track:
            raise ValueError('Incomplete comparison cannot claim completed audio')

def validate_manifest(data: dict, path: Path, *, verify_assets=True):
    if data.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Unsupported manifest schema version')
    if data.get('kind') not in {'voice', 'candidates'} or not isinstance(data.get('run_id'), str) or not data['run_id']:
        raise ValueError('Invalid manifest kind or run identity')
    def walk(value):
        if isinstance(value, dict):
            if 'path' in value:
                resolved = resolve_asset(path, value['path'])
                digest = value.get('sha256')
                if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
                    raise ValueError('Asset requires a SHA-256 checksum')
                if verify_assets and (not resolved.is_file() or sha256(resolved) != digest):
                    raise ValueError(f'Asset checksum mismatch or missing file: {value["path"]}')
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(data)
    def source_settings(config):
        if not isinstance(config, dict):
            raise ValueError('Synthesis settings are required')
        validate_speed(config.get('speed'))
        model = next((m for m in QWEN_INSTRUCTION_SAMPLE_CAPABILITIES.models if m.option.value == config.get('model')), None)
        if model is None or config.get('voice') not in {v.value for v in model.voices}:
            raise ValueError('Unsupported source model or voice')
        if config.get('instructions') and not model.supports_instructions:
            raise ValueError('Source model does not support instructions')
        if config.get('language') not in {'English', 'Chinese'} or config.get('audio_format') != 'pcm' or config.get('sample_rate') != 24000:
            raise ValueError('Invalid source audio or language settings')
        if not isinstance(config.get('instructions'), str) or len(config['instructions']) > 4000:
            raise ValueError('Invalid source instructions')
    if data['kind'] == 'voice':
        if not isinstance(data.get('voices'), list) or not data['voices']:
            raise ValueError('Voice manifest requires voices')
        keys = set()
        comparison_ids = set()
        for entry in data['voices']:
            key = entry.get('key', '')
            if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', key) or key in keys:
                raise ValueError('Voice keys must be unique stable lowercase keys')
            keys.add(key)
            if not isinstance(entry.get('name'), str) or not entry['name'].strip() or entry.get('language') not in {'en', 'zh'}:
                raise ValueError('Voice name and language are required')
            validate_speed(entry.get('speed'))
            if not isinstance(entry.get('reference'), dict) or not isinstance(entry['reference'].get('provenance'), dict):
                raise ValueError('Reference and provenance are required')
            enrollment = entry.get('enrollment')
            if enrollment:
                validate_voice_id(enrollment.get('voice'))
                if enrollment.get('target_model') != CLONE_MODEL:
                    raise ValueError('Unsupported clone target model')
            if not isinstance(entry.get('comparisons'), list):
                raise ValueError('Comparisons must be a list')
            _validate_comparisons(entry, path, source_settings, comparison_ids)
            if entry.get('acceptance'):
                if entry['acceptance'].get('key') != key:
                    raise ValueError('Acceptance key mismatch')
                validate_speed(entry['acceptance'].get('speed'))
    elif not isinstance(data.get('samples'), list):
        raise ValueError('Candidate manifest requires samples')

    if data['kind'] == 'candidates':
        numbers = set()
        for sample in data['samples']:
            if not isinstance(sample.get('number'), int) or sample['number'] < 1 or sample['number'] in numbers:
                raise ValueError('Candidate numbers must be unique positive integers')
            numbers.add(sample['number'])
            source_settings(sample.get('settings'))
            if sample.get('text_sha256') != data.get('text', {}).get('sha256'):
                raise ValueError('Candidate text identity differs')
            if sample.get('status') == 'completed' and not sample.get('audio'):
                raise ValueError('Completed candidate is missing audio')


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    validate_manifest(data, path)
    return data


def save_manifest(path: Path, manifest: dict) -> None:
    validate_manifest(manifest, path)
    serialized = json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            output.write(serialized)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

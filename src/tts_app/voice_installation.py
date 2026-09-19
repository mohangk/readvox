"""Validate offline clone installation inputs and preflight existing catalogs.

Workshop speed/instructions/preview fields describe the accepted evaluation.
They are retained in source manifests, not duplicated as active profile settings.
Installation owns voice identities and provenance only; every profile is editable.
"""
from __future__ import annotations
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, TypedDict
from tts_app.voice_storage import voice_record

CLONE_MODEL = 'qwen3-tts-vc-realtime-2026-01-15'


class CloneInstallation(TypedDict):
    key: str
    provider: str
    model: str
    voice: str
    language: str
    name: str
    speed: float
    instructions: str
    preview_text: str
    reference_path: str
    reference_sha256: str
    provenance: dict[str, Any]


def validate_clone_installation(value: dict) -> CloneInstallation:
    """Validate durable definitions independently of HTTP and filesystem access."""
    required = CloneInstallation.__required_keys__
    if set(value) != required:
        raise ValueError('Registered voice definition has missing or unknown fields')
    result = dict(value)
    for field, limit in [('key', 120), ('name', 120), ('voice', 120), ('preview_text', 50_000)]:
        text = result[field]
        if not isinstance(text, str) or not text.strip() or len(text) > limit:
            raise ValueError(f'Invalid clone installation {field}')
        result[field] = text.strip()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', result['key']):
        raise ValueError('Invalid clone installation key')
    if result['provider'] not in {'qwen', 'fake'} or result['model'] != CLONE_MODEL:
        raise ValueError('Unsupported clone installation provider or model')
    if result['language'] != 'en' or result['instructions'] != '':
        raise ValueError('Registered clones require English and empty instructions')
    speed = result['speed']
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or not 0.5 <= speed <= 2:
        raise ValueError('Invalid clone installation speed')
    path = result['reference_path']
    if not isinstance(path, str) or '\\' in path:
        raise ValueError('Invalid reference_path')
    parts = PurePosixPath(path).parts
    if len(parts) < 2 or parts[0] != 'voices' or '..' in parts:
        raise ValueError('Reference path must be relative beneath voices/')
    checksum = result['reference_sha256']
    if not isinstance(checksum, str) or not re.fullmatch('[0-9a-f]{64}', checksum):
        raise ValueError('Invalid reference_sha256')
    if not isinstance(result['provenance'], dict):
        raise ValueError('Invalid voice provenance')
    try:
        serialized = json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError('Voice definition must contain finite JSON values') from exc
    if json.loads(serialized) != result:
        raise ValueError('Voice definition must use JSON-native values')
    return result



def installation_voice(value):
    return dict(key=value['key'],provider=value['provider'],provider_voice_id=value['voice'],name=value['name'],
        kind='cloned',available=True,
        model=value['model'],languages=[value['language']],supports_instructions=False,
        metadata={field:value[field] for field in ('reference_path','reference_sha256','provenance')})


def preflight_voice_installations(db_path, definitions, *, reuse_unchanged_source=False):
    """Read-only validation also accepts a database awaiting the catalog migration."""
    validated=[validate_clone_installation(value) for value in definitions]
    if len({value['key'] for value in validated})!=len(validated):
        raise ValueError('Duplicate voice key')
    identities={(value['provider'],value['voice']) for value in validated}
    if len(identities)!=len(validated):
        raise ValueError('Duplicate provider voice identity')
    path=Path(db_path)
    if not path.exists():
        return validated
    import sqlite3
    from tts_app.voice_migrations import migrate_voice_catalog, preview_voice_database
    conn = preview_voice_database(path)
    conn.row_factory = sqlite3.Row
    with conn:
        migrate_voice_catalog(conn, validated[0]['provider'] if validated else 'qwen')
    try:
        tables={row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for index,definition in enumerate(validated):
            candidate=installation_voice(definition)
            existing=None
            if 'voices' in tables:
                row=conn.execute('SELECT * FROM voices WHERE key=?',(definition['key'],)).fetchone()
                if row:
                    existing={key:voice_record(row)[key] for key in candidate}
                identity=conn.execute('SELECT key FROM voices WHERE provider=? AND provider_voice_id=?',
                    (definition['provider'],definition['voice'])).fetchone()
                if identity and identity['key']!=definition['key']:
                    raise ValueError('Provider voice identity is already installed under another key')
            if existing:
                def content(value):
                    metadata=value['metadata']
                    return {**value,'metadata':{**metadata,'reference_path':None,'provenance':{
                        k:v for k,v in metadata['provenance'].items() if k!='source_manifest_sha256'}}}
                if existing!=candidate:
                    if not reuse_unchanged_source or content(existing)!=content(candidate):
                        raise ValueError(f"Voice {definition['key']} is already installed with different settings")
                    validated[index]={**definition,**existing['metadata']}
        return validated
    finally:
        conn.close()

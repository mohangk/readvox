"""One-time conversion of historical voice/profile schemas to voice-owned models."""
import json
from pathlib import Path
import subprocess
import sys
import sqlite3
from tempfile import TemporaryDirectory

from tts_app.profile_storage import ensure_profile_schema, PROFILE_FIELDS
from tts_app.voice_storage import ensure_voice_schema, insert_voice, validate_voice, validate_provider_definitions, voice_record, voice_values, VOICE_FIELDS

CATALOG_MIGRATION_VERSION = 4


def _sequence(conn, table, tables):
    if 'sqlite_sequence' not in tables:
        return 0
    row = conn.execute('SELECT seq FROM sqlite_sequence WHERE name=?', (table,)).fetchone()
    return row['seq'] if row else 0


def _restore_sequence(conn, table, previous):
    row = conn.execute('SELECT seq FROM sqlite_sequence WHERE name=?', (table,)).fetchone()
    if row is None:
        conn.execute('INSERT INTO sqlite_sequence(name,seq) VALUES(?,?)', (table, previous))
    elif row['seq'] < previous:
        conn.execute('UPDATE sqlite_sequence SET seq=? WHERE name=?', (previous, table))


def _flat_legacy_voice(row, reviewed):
    """Legacy graphs exist only while this forward migration is running."""
    value = {key: row[key] for key in ('key', 'provider', 'provider_voice_id', 'name', 'kind')}
    value.update(available=bool(row['available']), metadata=json.loads(row['metadata_json']))
    known = reviewed.get((row['provider'], row['provider_voice_id']))
    if row['kind'] == 'builtin' and known:
        return {**value, **{key: known[key] for key in ('model', 'languages', 'supports_instructions')}}
    models = json.loads(row['models_json'])
    if row['kind'] == 'cloned':
        enrollment = value['metadata'].get('provenance', {}).get('enrollment', {})
        model = enrollment.get('target_model')
        if model is None and len(models) == 1:
            model = next(iter(models))
    else:
        model = next(iter(models)) if len(models) == 1 else None
    if not model or model not in models:
        raise ValueError('No unambiguous model binding')
    capability = models[model]
    return {**value, 'model': model, 'languages': capability['languages'],
            'supports_instructions': capability['supports_instructions']}


def migrate_voice_catalog(conn, provider_name):
    """Called within a transaction; report authorized cleanup without touching media."""
    from tts_app.providers.qwen_catalog import qwen_voice_definitions

    if not isinstance(provider_name, str) or not provider_name.strip():
        raise ValueError('A provider name is required for migration')
    conn.execute('CREATE TABLE IF NOT EXISTS profile_migrations (version INTEGER PRIMARY KEY)')
    report = dict(schema_upgraded=False, deleted_profiles=[], deleted_voices=[], model_changes=[])
    if conn.execute('SELECT 1 FROM profile_migrations WHERE version=?', (CATALOG_MIGRATION_VERSION,)).fetchone():
        return report
    tables = {row['name'] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    profiles = [dict(row) for row in conn.execute('SELECT * FROM voice_profiles ORDER BY id')] if 'voice_profiles' in tables else []
    old_voices = [dict(row) for row in conn.execute('SELECT * FROM voices ORDER BY id')] if 'voices' in tables else []
    profile_sequence = _sequence(conn, 'voice_profiles', tables)
    voice_sequence = _sequence(conn, 'voices', tables)
    source = validate_provider_definitions('qwen', qwen_voice_definitions())
    reviewed = {(value['provider'], value['provider_voice_id']): value for value in source}
    voices, installation_keys = {}, {}
    for row in old_voices:
        try:
            value = validate_voice(_flat_legacy_voice(row, reviewed) if 'models_json' in row else
                                   {key: voice_record(row)[key] for key in VOICE_FIELDS})
            voices[row['id']] = {**value, **{key: row[key] for key in ('id', 'created_at', 'updated_at')}}
            old_models = sorted(json.loads(row['models_json'])) if 'models_json' in row else [row['model']]
            if old_models != [value['model']]:
                report['model_changes'].append(dict(table='voices', id=row['id'], before=old_models, after=value['model']))
        except (ValueError, KeyError, TypeError) as exc:
            report['deleted_voices'].append(dict(id=row['id'], key=row['key'], reason=str(exc)))
    next_id = max([voice_sequence, *voices.keys()], default=0) + 1
    if 'registered_voices' in tables:
        groups = {}
        for row in conn.execute('SELECT * FROM registered_voices ORDER BY rowid'):
            definition = json.loads(row['definition_json'])
            groups.setdefault((definition['provider'], definition['voice']), []).append((definition, row['created_at']))
        for identity, entries in groups.items():
            first, timestamp = entries[0]
            models = {definition['model'] for definition, _ in entries}
            if len(models) != 1:
                for definition, _ in entries:
                    report['deleted_voices'].append(dict(key=definition['system_key'], reason='Conflicting enrolled model bindings'))
                continue
            metadata = {key: first[key] for key in ('reference_path', 'reference_sha256', 'provenance')}
            if len(entries) > 1:
                metadata['provenance'] = {**metadata['provenance'], 'legacy_registrations': [definition for definition, _ in entries]}
            value = validate_voice(dict(key=first['system_key'], provider=identity[0], provider_voice_id=identity[1],
                name=first['name'], kind='cloned', available=True, model=first['model'],
                languages=sorted({definition['language'] for definition, _ in entries}), supports_instructions=False, metadata=metadata))
            voices[next_id] = {**value, 'id': next_id, 'created_at': timestamp, 'updated_at': timestamp}
            for definition, _ in entries:
                installation_keys[definition['system_key']] = next_id
            next_id += 1
    identities = {(value['provider'], value['provider_voice_id']): id for id, value in voices.items()}
    migrated_profiles = []
    for row in profiles:
        voice_id = row.get('voice_id')
        if voice_id is None:
            voice_id = installation_keys.get(row.get('system_key'))
            identity = (provider_name, row.get('voice'))
            if voice_id is None:
                voice_id = identities.get(identity)
            if voice_id is None and identity in reviewed:
                value = reviewed[identity]
                voice_id = next_id
                next_id += 1
                voices[voice_id] = {**value, 'id': voice_id, 'created_at': row['created_at'], 'updated_at': row['updated_at']}
                identities[identity] = voice_id
        value = voices.get(voice_id)
        reason = None
        if value is None:
            reason = 'Unresolvable voice identity or model binding'
        elif row['language'] not in value['languages']:
            reason = 'Language is unsupported by the voice'
        elif row['instructions'].strip() and not value['supports_instructions']:
            reason = 'Instructions are unsupported by the voice'
        if reason:
            report['deleted_profiles'].append(dict(id=row['id'], reason=reason))
            continue
        if row.get('model') != value['model']:
            report['model_changes'].append(dict(table='voice_profiles', id=row['id'], before=row.get('model'), after=value['model']))
        migrated_profiles.append({**row, 'voice_id': voice_id})
    # Drop the referencing table first so foreign-key enforcement remains enabled.
    if 'voice_profiles' in tables:
        conn.execute('DROP TABLE voice_profiles')
    if 'voices' in tables:
        conn.execute('DROP TABLE voices')
    ensure_voice_schema(conn)
    ensure_profile_schema(conn)
    for id, value in sorted(voices.items()):
        conn.execute('''INSERT INTO voices (id,key,provider,provider_voice_id,name,kind,available,model,
            languages_json,supports_instructions,metadata_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (id,) + voice_values(value) + (value['created_at'], value['updated_at']))
    for row in migrated_profiles:
        fields = ('id', *PROFILE_FIELDS, 'name_key', 'created_at', 'updated_at')
        conn.execute('INSERT INTO voice_profiles (' + ','.join(fields) + ') VALUES(' + ','.join('?' for _ in fields) + ')',
                     tuple(row[field] for field in fields))
    _restore_sequence(conn, 'voices', voice_sequence)
    _restore_sequence(conn, 'voice_profiles', profile_sequence)
    if 'registered_voices' in tables:
        conn.execute('DROP TABLE registered_voices')
    conn.execute('INSERT OR IGNORE INTO profile_migrations VALUES(3)')
    conn.execute('INSERT INTO profile_migrations VALUES(?)', (CATALOG_MIGRATION_VERSION,))
    report['schema_upgraded'] = True
    return report


def preview_voice_database(path):
    """Snapshot a quiescent POSIX database without changing any source files."""
    conn = sqlite3.connect(':memory:')
    try:
        if path.exists():
            with TemporaryDirectory(prefix='readvox-catalog-check-') as directory:
                snapshot = Path(directory) / 'app.db'
                # An explicit file path ensures the worker uses this checkout,
                # independently of a virtualenv's editable package installation.
                worker = Path(__file__).with_name('voice_catalog_snapshot.py')
                result = subprocess.run([sys.executable, str(worker), str(path), str(snapshot)],
                                        capture_output=True, text=True)
                if result.returncode:
                    raise ValueError(result.stderr.strip() or 'Cannot safely snapshot catalog database')
                source = sqlite3.connect(snapshot)
                try:
                    source.backup(conn)
                finally:
                    source.close()
        return conn
    except BaseException:
        conn.close()
        raise

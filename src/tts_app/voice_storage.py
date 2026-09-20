"""Flat provider voice identities and their exact synthesis bindings."""
from __future__ import annotations

import hashlib
import json

VOICE_FIELDS = ('key', 'provider', 'provider_voice_id', 'name', 'kind', 'available',
                'model', 'languages', 'supports_instructions', 'metadata')


def builtin_voice_key(provider, voice):
    return f'builtin-{provider}-' + hashlib.sha256(voice.encode()).hexdigest()[:24]


def ensure_voice_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS voices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL UNIQUE,
        provider TEXT NOT NULL,
        provider_voice_id TEXT NOT NULL,
        name TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('builtin', 'cloned')),
        available INTEGER NOT NULL CHECK(available IN (0, 1)),
        model TEXT NOT NULL CHECK(length(trim(model)) > 0),
        languages_json TEXT NOT NULL,
        supports_instructions INTEGER NOT NULL CHECK(supports_instructions IN (0, 1)),
        metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(provider, provider_voice_id)
    )''')


def voice_record(row):
    result = dict(row)
    result['available'] = bool(result['available'])
    result['supports_instructions'] = bool(result['supports_instructions'])
    result['languages'] = json.loads(result.pop('languages_json'))
    result['metadata'] = json.loads(result.pop('metadata_json'))
    return result


def validate_voice(value):
    result = dict(value)
    if set(result) != set(VOICE_FIELDS):
        raise ValueError('Voice catalog entry has missing or unknown fields')
    for field in ('key', 'provider', 'provider_voice_id', 'name', 'model'):
        if not isinstance(result[field], str) or not result[field].strip() or len(result[field]) > 256:
            raise ValueError(f'Invalid voice {field}')
        result[field] = result[field].strip()
    if result['kind'] not in ('builtin', 'cloned') or not isinstance(result['available'], bool):
        raise ValueError('Invalid voice kind or availability')
    languages = result['languages']
    if (not isinstance(languages, list) or not languages
            or any(language not in ('en', 'zh') for language in languages)
            or len(set(languages)) != len(languages)
            or not isinstance(result['supports_instructions'], bool)):
        raise ValueError('Invalid voice capabilities')
    result['languages'] = sorted(languages)
    if not isinstance(result['metadata'], dict):
        raise ValueError('Voice metadata must be an object')
    try:
        if json.loads(json.dumps(result, allow_nan=False)) != result:
            raise ValueError('Voice metadata must use JSON-native values')
    except (TypeError, ValueError) as exc:
        raise ValueError('Voice metadata must contain finite JSON values') from exc
    return result


def voice_values(value):
    return (value['key'], value['provider'], value['provider_voice_id'], value['name'],
        value['kind'], value['available'], value['model'], json.dumps(value['languages']),
        value['supports_instructions'], json.dumps(value['metadata'], sort_keys=True))


def insert_voice(conn, value):
    return conn.execute('''INSERT INTO voices
        (key,provider,provider_voice_id,name,kind,available,model,languages_json,supports_instructions,metadata_json)
        VALUES(?,?,?,?,?,?,?,?,?,?)''', voice_values(validate_voice(value))).lastrowid


def validate_provider_definitions(provider_name, definitions):
    values = [validate_voice(value) for value in definitions]
    if not values:
        raise ValueError('Provider catalog source must not be empty')
    if any(value['provider'] != provider_name or value['kind'] != 'builtin' for value in values):
        raise ValueError('Provider sync accepts only its own built-in voices')
    if len({value['key'] for value in values}) != len(values):
        raise ValueError('Duplicate voice key')
    if len({value['provider_voice_id'] for value in values}) != len(values):
        raise ValueError('Duplicate provider voice identity')
    return values


def reconcile_provider_voices(conn, provider_name, definitions):
    """Reconcile in the caller's transaction, preserving profiles and retired IDs."""
    values = validate_provider_definitions(provider_name, definitions)
    report = dict(added=[], updated=[], unchanged=[], retired=[], model_changes=[])
    active = {value['provider_voice_id'] for value in values}
    for value in values:
        row = conn.execute('SELECT * FROM voices WHERE key=? OR (provider=? AND provider_voice_id=?)',
            (value['key'], provider_name, value['provider_voice_id'])).fetchall()
        if not row:
            insert_voice(conn, value)
            report['added'].append(value['key'])
            continue
        if (len(row) != 1 or row[0]['kind'] != 'builtin' or row[0]['key'] != value['key']
                or row[0]['provider'] != provider_name or row[0]['provider_voice_id'] != value['provider_voice_id']):
            raise ValueError('Provider voice identity conflicts with the catalog')
        existing = voice_record(row[0])
        if all(existing[key] == value[key] for key in VOICE_FIELDS):
            report['unchanged'].append(value['key'])
            continue
        if existing['model'] != value['model']:
            report['model_changes'].append(dict(key=value['key'], id=existing['id'],
                before=existing['model'], after=value['model']))
        conn.execute('''UPDATE voices SET key=?,provider=?,provider_voice_id=?,name=?,kind=?,available=?,
            model=?,languages_json=?,supports_instructions=?,metadata_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?''',
            voice_values(value) + (existing['id'],))
        report['updated'].append(value['key'])
    for row in conn.execute("SELECT id,key,provider_voice_id,available FROM voices WHERE provider=? AND kind='builtin'", (provider_name,)):
        if row['provider_voice_id'] not in active and row['available']:
            conn.execute('UPDATE voices SET available=0,updated_at=CURRENT_TIMESTAMP WHERE id=?', (row['id'],))
            report['retired'].append(row['key'])
    for key in ('added', 'updated', 'unchanged', 'retired'):
        report[key].sort()
    report['model_changes'].sort(key=lambda change: change['key'])
    return report


class VoiceStorageMixin:
    def list_voices(self, provider_name=None):
        with self.connection() as conn:
            rows = conn.execute('SELECT * FROM voices WHERE provider=? ORDER BY id', (provider_name,)) if provider_name else conn.execute('SELECT * FROM voices ORDER BY id')
            return [voice_record(row) for row in rows]

    def get_voice(self, voice_id):
        with self.connection() as conn:
            row = conn.execute('SELECT * FROM voices WHERE id=?', (voice_id,)).fetchone()
            if row is None:
                raise KeyError(voice_id)
            return voice_record(row)

    def sync_provider_voices(self, provider_name, definitions):
        values = validate_provider_definitions(provider_name, definitions)
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            return reconcile_provider_voices(conn, provider_name, values)

    def install_voices(self, definitions):
        """Install immutable identities; installation never owns profiles."""
        values = [validate_voice(value) for value in definitions]
        if len({value['key'] for value in values}) != len(values):
            raise ValueError('Duplicate voice key')
        if len({(value['provider'], value['provider_voice_id']) for value in values}) != len(values):
            raise ValueError('Duplicate provider voice identity')
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            ids = []
            for value in values:
                row = conn.execute('SELECT * FROM voices WHERE key=?', (value['key'],)).fetchone()
                if row:
                    if any(voice_record(row)[key] != value[key] for key in VOICE_FIELDS):
                        raise ValueError(f"Voice {value['key']} is already installed with different settings")
                    ids.append(row['id'])
                else:
                    if conn.execute('SELECT 1 FROM voices WHERE provider=? AND provider_voice_id=?',
                            (value['provider'], value['provider_voice_id'])).fetchone():
                        raise ValueError('Provider voice identity is already installed under another key')
                    ids.append(insert_voice(conn, value))
            return [voice_record(conn.execute('SELECT * FROM voices WHERE id=?', (id,)).fetchone()) for id in ids]

"""Initialize the current voice catalog and editable profile schema."""
from tts_app.profile_storage import ensure_profile_schema
from tts_app.voice_storage import ensure_voice_schema


def ensure_current_voice_schema(conn):
    """Create absent tables; reject unsupported schemas before any writes.

    Existing catalog/profile records and sequence counters are never rebuilt.
    The historical profile_migrations table now only records default seeding
    (version 1). Existing higher-version rows are inert and remain untouched.
    """
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {
        'voices': {'id', 'key', 'provider', 'provider_voice_id', 'name', 'kind',
                   'available', 'model', 'languages_json', 'supports_instructions',
                   'metadata_json', 'created_at', 'updated_at'},
        'voice_profiles': {'id', 'name', 'name_key', 'voice_id', 'language', 'speed',
                           'instructions', 'preview_text', 'created_at', 'updated_at'},
        'profile_migrations': {'version'},
    }
    if 'registered_voices' in tables:
        raise ValueError('Unsupported voice schema: registered_voices is obsolete; use a current-schema database')
    for table, columns in expected.items():
        if table in tables and {row[1] for row in conn.execute(f'PRAGMA table_info({table})')} != columns:
            raise ValueError(f'Unsupported voice schema: {table}; use a current-schema database')
    ensure_voice_schema(conn)
    ensure_profile_schema(conn)
    conn.execute('CREATE TABLE IF NOT EXISTS profile_migrations (version INTEGER PRIMARY KEY)')

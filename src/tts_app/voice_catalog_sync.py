"""Explicit, credential-free catalog population using reviewed source definitions."""
from pathlib import Path
import sqlite3

from tts_app.providers.qwen_catalog import qwen_voice_definitions
from tts_app.voice_migrations import migrate_voice_catalog, preview_voice_database
from tts_app.voice_storage import reconcile_provider_voices, validate_provider_definitions



def sync_voice_catalog(settings, provider_name='qwen', check_only=False, *, definitions=None):
    """Explicit provider owns provider-less legacy identities during migration.

    Routine sync never cleans profiles. Preflight requires a quiescent POSIX DB;
    busy connections fail before writes instead of producing a mixed snapshot.
    """
    if provider_name != 'qwen':
        raise ValueError('Catalog population supports provider qwen only')
    if settings.provider_name not in ('qwen', 'fake'):
        raise ValueError(f'unknown TTS provider: {settings.provider_name}')
    values = validate_provider_definitions(provider_name,
        qwen_voice_definitions() if definitions is None else definitions)
    path = Path(settings.db_path).resolve()
    existed = path.exists()
    # Preflight on a private SQLite copy before any target file/directory creation.
    preview = preview_voice_database(path)
    preview.row_factory = sqlite3.Row
    preview.execute('PRAGMA foreign_keys=ON')
    try:
        with preview:
            preview.execute('BEGIN IMMEDIATE')
            migration = migrate_voice_catalog(preview, provider_name)
            changes = reconcile_provider_voices(preview, provider_name, values)
        report = dict(target=str(path), provider=provider_name, migration_provider=provider_name, check_only=check_only,
            target_exists=existed, schema_upgraded=migration['schema_upgraded'], migration=migration, **changes)
    finally:
        preview.close()
    if check_only:
        return report
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            migration = migrate_voice_catalog(conn, provider_name)
            changes = reconcile_provider_voices(conn, provider_name, values)
        return {**report, 'schema_upgraded': migration['schema_upgraded'], 'migration': migration, **changes}
    finally:
        conn.close()

"""Editable named reading presets referencing the backend-managed voice catalog.

All profiles have the same lifecycle. Built-in and cloned voices share voice_id;
profile deletion never owns the voice, enrollment, reference files or History.
"""
from __future__ import annotations

PROFILE_FIELDS = ('name','voice_id','language','speed','instructions','preview_text')
PROFILE_SELECT = '''SELECT p.*, v.provider, v.provider_voice_id AS voice,
    v.name AS voice_name, v.key AS voice_key, v.available AS voice_available
    FROM voice_profiles p JOIN voices v ON v.id=p.voice_id'''


def ensure_profile_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS voice_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL CHECK(length(trim(name)) > 0),
        name_key TEXT NOT NULL UNIQUE,
        voice_id INTEGER NOT NULL REFERENCES voices(id) ON DELETE RESTRICT,
        language TEXT NOT NULL CHECK(language IN ('en', 'zh')),
        speed REAL NOT NULL CHECK(speed BETWEEN 0.5 AND 2.0),
        instructions TEXT NOT NULL,
        preview_text TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_voice_profiles_voice_id ON voice_profiles(voice_id)')


def insert_profile(conn, values):
    return conn.execute('INSERT INTO voice_profiles ('+','.join(PROFILE_FIELDS)+',name_key) VALUES(?,?,?,?,?,?,?)',
        tuple(values[field] for field in PROFILE_FIELDS)+(values['name'].casefold(),)).lastrowid


class ProfileStorageMixin:
    def initialize_voice_profiles(self, defaults):
        """Seed once using the retained version-1 marker; deletions stay deleted."""
        if not defaults:
            return
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if conn.execute('SELECT 1 FROM profile_migrations WHERE version=1').fetchone():
                return
            for profile in defaults:
                if conn.execute('SELECT 1 FROM voice_profiles WHERE name_key=?', (profile['name'].casefold(),)).fetchone():
                    continue
                values=self._profile_values(conn,profile)
                insert_profile(conn,values)
            conn.execute('INSERT INTO profile_migrations VALUES(1)')

    def _profile_values(self, conn, values):
        result=dict(values)
        if result.get('voice_id') is None:
            raise ValueError('Profiles require a catalog voice_id')
        return result

    def list_voice_profiles(self):
        with self.connection() as conn:
            return [dict(row) for row in conn.execute(PROFILE_SELECT+' ORDER BY p.id')]

    def get_voice_profile(self, profile_id):
        with self.connection() as conn:
            row=conn.execute(PROFILE_SELECT+' WHERE p.id=?',(profile_id,)).fetchone()
            if row is None:
                raise KeyError(profile_id)
            return dict(row)

    def save_voice_profile(self, values, profile_id=None):
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            values=self._profile_values(conn,values)
            if profile_id is None:
                profile_id=insert_profile(conn,values)
            else:
                cursor=conn.execute('UPDATE voice_profiles SET '+','.join(field+'=?' for field in PROFILE_FIELDS)
                    +',name_key=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                    tuple(values[field] for field in PROFILE_FIELDS)+(values['name'].casefold(),profile_id))
                if not cursor.rowcount:
                    raise KeyError(profile_id)
        return self.get_voice_profile(profile_id)

    def delete_voice_profile(self, profile_id):
        with self.connection() as conn:
            if not conn.execute('DELETE FROM voice_profiles WHERE id=?',(profile_id,)).rowcount:
                raise KeyError(profile_id)

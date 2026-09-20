"""Private catalog preflight snapshot, using POSIX SQLite-compatible file locks.

Copy in a separate process: POSIX record locks held by SQLite connections in the
calling process must conflict with the copy lock too. No source SQLite connection is
opened, so recovery and WAL shared-memory creation happen only on the copy.
"""
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory


def copy_locked_database(path, snapshot):
    try:
        import fcntl
    except ImportError as exc:
        raise ValueError('Catalog preflight requires POSIX file locking') from exc
    # SQLite's Unix VFS places every rollback/WAL database lock on byte ranges
    # in the main file. Locking the whole file conflicts with readers, writers,
    # and checkpoint-capable WAL connections, including idle WAL connections.
    # Opening r+b permits an exclusive record lock without writing source bytes.
    with path.open('r+b') as source:
        try:
            fcntl.lockf(source, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('Close the Readvox app and all database connections, then retry catalog preflight; the database is busy') from exc
        # Keep this exact descriptor open throughout the copy: closing another
        # descriptor for the same inode would release this process's locks.
        with snapshot.open('wb') as target:
            shutil.copyfileobj(source, target)
        for suffix in ('-wal', '-journal'):
            sidecar = Path(str(path) + suffix)
            if sidecar.exists():
                shutil.copyfile(sidecar, Path(str(snapshot) + suffix))
        # The OS releases the lock when source closes. No retry or source recovery.


def preview_voice_database(path):
    """Snapshot a quiescent POSIX database without changing any source files."""
    conn = sqlite3.connect(':memory:')
    try:
        if path.exists():
            with TemporaryDirectory(prefix='readvox-catalog-check-') as directory:
                snapshot = Path(directory) / 'app.db'
                # An explicit file path ensures the worker uses this checkout,
                # independently of a virtualenv's editable package installation.
                worker = Path(__file__).resolve()
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


if __name__ == '__main__':
    try:
        copy_locked_database(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

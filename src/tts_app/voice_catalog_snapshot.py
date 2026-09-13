"""Private catalog preflight snapshot, using POSIX SQLite-compatible file locks.

Run as a separate process: POSIX record locks held by SQLite connections in the
calling process must conflict with this lock too. No source SQLite connection is
opened, so recovery and WAL shared-memory creation happen only on the copy.
"""
from pathlib import Path
import shutil
import sys


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


if __name__ == '__main__':
    try:
        copy_locked_database(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

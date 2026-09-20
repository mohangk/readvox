#!/usr/bin/env python3
"""Populate/update reviewed Qwen presets without provider credentials or calls."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from tts_app.config import load_settings
from tts_app.voice_catalog_sync import sync_voice_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=['qwen'], default='qwen',
        help='Catalog provider (default: qwen)')
    parser.add_argument('--data-dir', type=Path, help='Override all target data paths, including TTS_DB_PATH')
    parser.add_argument('--check', action='store_true', help='Report without modifying target files; close database connections first (POSIX locking required)')
    args = parser.parse_args()
    settings = load_settings()
    if args.data_dir:
        directory = args.data_dir.resolve()
        settings = replace(settings, data_dir=directory, db_path=directory / 'app.db',
            audio_dir=directory / 'audio', image_dir=directory / 'images')
    try:
        report = sync_voice_catalog(settings, args.provider, args.check)
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Catalog population failed: {exc}\n')
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()

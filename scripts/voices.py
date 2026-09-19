#!/usr/bin/env python3
"""Resolve this checkout's sources, then delegate to the voice workshop CLI."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from tts_app.voice_tools.cli import main

if __name__ == '__main__':
    raise SystemExit(main())

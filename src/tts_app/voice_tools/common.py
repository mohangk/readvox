"""Local run preparation and synthesis shared by operator commands."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from uuid import uuid4

from tts_app.providers.base import TTSOptions
from tts_app.providers.options import QWEN_INSTRUCTION_SAMPLE_CAPABILITIES
from tts_app.voice_tools.audio import asset, write_track
from tts_app.voice_tools.manifest import validate_speed


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def new_run(output: Path, kind: str):
    output.mkdir(parents=True, exist_ok=False)
    return {'schema_version': 1, 'kind': kind, 'run_id': output.name + '-' + uuid4().hex[:8], 'created_at': timestamp()}


def read_text(path: Path) -> str:
    text = path.read_text(encoding='utf-8')
    if not text.strip() or len(text) > 2000:
        raise ValueError('Each synthesis passage must contain 1–2000 characters')
    return text


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def settings(*, voice, model, language='en', speed=1.0, instructions='') -> dict:
    validate_speed(speed)
    if language not in {'en', 'zh'}:
        raise ValueError('Language must be en or zh')
    if len(instructions) > 4000:
        raise ValueError('Instructions exceed 4000 characters')
    capability = next((m for m in QWEN_INSTRUCTION_SAMPLE_CAPABILITIES.models if m.option.value == model), None)
    if capability is None or voice not in {v.value for v in capability.voices}:
        raise ValueError('Unsupported source model or voice')
    if instructions and not capability.supports_instructions:
        raise ValueError('Source model does not support instructions')
    return asdict(TTSOptions(voice=voice, model=model, language={'en': 'English', 'zh': 'Chinese'}[language], speed=speed, instructions=instructions, audio_format='pcm'))


async def synthesize(provider, text, options, path):
    chunks = [chunk.data async for chunk in provider.stream_speech(text, TTSOptions(**options))]
    write_track(path, chunks, options['sample_rate'])
    return asset(path, path.parent), sum(map(len, chunks)) / (2 * options['sample_rate'])

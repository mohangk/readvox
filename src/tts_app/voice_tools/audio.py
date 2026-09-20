"""Owned WAV artifacts and measured PCM boundaries."""
import hashlib
from pathlib import Path
import wave


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def asset(path: Path, root: Path) -> dict:
    return {'path': path.relative_to(root).as_posix(), 'sha256': sha256(path)}


def write_track(path: Path, chunks: list[bytes], sample_rate: int = 24000) -> list[float]:
    if not chunks or any(not chunk or len(chunk) % 2 for chunk in chunks):
        raise ValueError('Expected nonempty 16-bit PCM audio')
    boundaries, frames = [], 0
    with wave.open(str(path), 'wb') as track:
        track.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))
        for chunk in chunks:
            boundaries.append(frames / sample_rate)
            track.writeframes(chunk)
            frames += len(chunk) // 2
    return boundaries


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path)) as audio:
        return audio.readframes(audio.getnframes())


# The enrollment adapter owns the provider reference limits.
from tts_app.providers.qwen_enrollment import validate_reference  # noqa: E402,F401

"""Explicit audio-only enrollment and read-only recovery; never retries create."""
import base64
import hashlib
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import uuid4
import wave

import httpx

from tts_app.providers.base import ProviderError
CLONE_MODEL = 'qwen3-tts-vc-realtime-2026-01-15'


def validate_voice_id(voice):
    if not isinstance(voice, str) or not re.fullmatch(r'qwen-tts-vc-[A-Za-z0-9_-]+', voice):
        raise ValueError('Invalid Qwen cloned voice ID')


def preferred_name(key: str) -> str:
    return re.sub('[^a-zA-Z0-9]', '', key)[:10] + uuid4().hex[:6]


class QwenEnrollment:
    def __init__(self, api_key, endpoint, *, client, target_model=CLONE_MODEL):
        remote = urlsplit(endpoint)
        if remote.scheme != 'https' or remote.hostname not in {'dashscope-intl.aliyuncs.com', 'dashscope.aliyuncs.com', 'dashscope-us.aliyuncs.com'} or remote.username or remote.password or remote.port:
            raise ValueError('Enrollment requires a supported HTTPS Qwen endpoint')
        if target_model != CLONE_MODEL:
            raise ValueError('Unsupported clone target model')
        self.api_key, self.endpoint, self.client, self.target_model = api_key, endpoint, client, target_model
        self.endpoint_region = remote.hostname
        # A credential fingerprint, not a durable account identifier; key rotation changes it.
        self.account_fingerprint = hashlib.sha256(api_key.encode()).hexdigest() if api_key else None

    async def _request(self, body):
        if not self.api_key:
            raise ProviderError('Qwen credentials are required for enrollment')
        try:
            response = await self.client.post(self.endpoint, json={'model': 'qwen-voice-enrollment', 'input': body}, headers={'Authorization': f'Bearer {self.api_key}'})
            if response.status_code != 200:
                raise ProviderError(f'Qwen enrollment failed (HTTP {response.status_code})')
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get('output'), dict):
                raise ProviderError('Qwen enrollment returned invalid output')
            return data
        except (httpx.HTTPError, ValueError) as error:
            raise ProviderError(f'Qwen enrollment failed ({type(error).__name__})') from error

    async def create(self, path: Path, name: str):
        validate_reference(path)
        if not re.fullmatch('[A-Za-z0-9_]{1,16}', name):
            raise ValueError('Preferred name must contain 1–16 letters, digits or underscores')
        data = await self._request({'action': 'create', 'target_model': self.target_model, 'preferred_name': name, 'language': 'en', 'audio': {'data': 'data:audio/wav;base64,' + base64.b64encode(path.read_bytes()).decode()}})
        output = data['output']
        try:
            validate_voice_id(output.get('voice'))
        except ValueError as error:
            raise ProviderError('Qwen enrollment returned no valid voice') from error
        if output.get('target_model') != self.target_model:
            raise ProviderError('Qwen enrollment returned a different target model')
        return {key: output[key] for key in ('voice', 'target_model', 'fallback_mode', 'fallback_reason') if key in output} | {'request_id': data.get('request_id'), 'preferred_name': name, 'endpoint_region': self.endpoint_region, 'account_fingerprint': self.account_fingerprint}

    async def lookup(self, *, page_index=0, page_size=100):
        if page_index < 0 or not 1 <= page_size <= 100:
            raise ValueError('Invalid lookup pagination')
        return (await self._request({'action': 'list', 'page_index': page_index, 'page_size': page_size}))['output']


def validate_reference(path: Path) -> dict:
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError('Reference exceeds 10 MB')
    try:
        with wave.open(str(path)) as audio:
            duration = audio.getnframes() / audio.getframerate()
            if (audio.getnchannels() != 1 or audio.getsampwidth() != 2
                    or audio.getframerate() < 24000 or not 3 <= duration <= 60):
                raise ValueError('Reference must be 3–60 seconds of mono 16-bit WAV at 24 kHz or higher')
            if len(audio.readframes(audio.getnframes())) != audio.getnframes() * 2:
                raise ValueError('Reference WAV is truncated')
            return {'duration': duration, 'sample_rate': audio.getframerate(), 'channels': 1, 'sample_width': 2}
    except (wave.Error, EOFError) as error:
        raise ValueError('Reference must be a valid WAV') from error

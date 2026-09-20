from __future__ import annotations

import base64
import json

import pytest

from tts_app.providers.base import ProviderError, TTSOptions
from tts_app.providers.qwen import QwenTTSProvider


@pytest.mark.asyncio
async def test_qwen_provider_requires_api_key():
    provider = QwenTTSProvider(
        api_key=None,
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
    )

    with pytest.raises(ProviderError, match="API key is required"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Cherry")):
            pass


@pytest.mark.asyncio
async def test_qwen_provider_sends_realtime_events_and_yields_audio():
    websocket = FakeWebSocket(
        [
            {"type": "session.created"},
            {"type": "session.updated"},
            {"type": "input_text_buffer.committed"},
            {"type": "response.created"},
            {"type": "response.audio.delta", "delta": base64.b64encode(b"abc").decode("ascii")},
            {"type": "response.audio.delta", "delta": base64.b64encode(b"def").decode("ascii")},
            {"type": "response.done", "response": {"status": "completed"}},
            {"type": "response.audio.delta", "delta": base64.b64encode(b"ignored").decode("ascii")},
        ]
    )
    captured = {}

    async def connect(url, additional_headers):
        captured["url"] = url
        captured["headers"] = additional_headers
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )
    options = TTSOptions(voice="Cherry", audio_format="mp3", language="Chinese", sample_rate=16000, speed=1.25)

    chunks = [chunk async for chunk in provider.stream_speech("hello", options)]

    assert [chunk.data for chunk in chunks] == [b"abc", b"def"]
    assert all(chunk.mime_type == "audio/mpeg" for chunk in chunks)
    assert all(chunk.extension == "mp3" for chunk in chunks)
    assert captured["url"] == "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime?model=qwen3-tts-flash-realtime"
    assert captured["headers"] == {"Authorization": "Bearer key"}
    assert [event["type"] for event in websocket.sent_events] == [
        "session.update",
        "input_text_buffer.append",
        "input_text_buffer.commit",
    ]
    assert websocket.sent_events[0]["session"]["voice"] == "Cherry"
    assert websocket.sent_events[0]["session"]["mode"] == "commit"
    assert websocket.sent_events[0]["session"]["language_type"] == "Chinese"
    assert websocket.sent_events[0]["session"]["response_format"] == "mp3"
    assert websocket.sent_events[0]["session"]["sample_rate"] == 16000
    assert websocket.sent_events[0]["session"]["speech_rate"] == 1.25
    assert "instructions" not in websocket.sent_events[0]["session"]
    assert websocket.sent_events[1]["text"] == "hello"
    assert websocket.closed is True


@pytest.mark.asyncio
async def test_qwen_provider_sends_instruction_control_when_present():
    websocket = FakeWebSocket(
        [
            {"type": "response.audio.delta", "delta": base64.b64encode(b"abc").decode("ascii")},
            {"type": "response.done", "response": {"status": "completed"}},
        ]
    )

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-instruct-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )
    options = TTSOptions(
        voice="Kai",
        audio_format="mp3",
        language="English",
        speed=0.9,
        instructions="Read in a calm long-form audiobook style.",
    )

    chunks = [chunk async for chunk in provider.stream_speech("hello", options)]

    assert [chunk.data for chunk in chunks] == [b"abc"]
    assert websocket.sent_events[0]["session"]["instructions"] == "Read in a calm long-form audiobook style."


@pytest.mark.asyncio
async def test_qwen_provider_uses_request_model_override():
    websocket = FakeWebSocket(
        [
            {"type": "response.audio.delta", "delta": base64.b64encode(b"abc").decode("ascii")},
            {"type": "response.done", "response": {"status": "completed"}},
        ]
    )
    captured = {}

    async def connect(url, additional_headers):
        captured["url"] = url
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )
    options = TTSOptions(voice="Kai", model="qwen3-tts-instruct-flash-realtime-2026-01-22")

    chunks = [chunk async for chunk in provider.stream_speech("hello", options)]

    assert [chunk.data for chunk in chunks] == [b"abc"]
    assert captured["url"].endswith("?model=qwen3-tts-instruct-flash-realtime-2026-01-22")


@pytest.mark.asyncio
async def test_qwen_provider_rejects_incomplete_response():
    websocket = FakeWebSocket([{"type": "response.done", "response": {"status": "incomplete"}}])

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="response did not complete successfully"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Cherry")):
            pass


@pytest.mark.asyncio
async def test_qwen_provider_rejects_completed_response_without_audio():
    websocket = FakeWebSocket([{"type": "response.done", "response": {"status": "completed"}}])

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="returned no audio"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Cherry")):
            pass


@pytest.mark.asyncio
async def test_qwen_provider_turns_server_error_into_provider_error():
    websocket = FakeWebSocket([{"type": "error", "error": {"message": "bad voice"}}])

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="PROVIDER_ERROR"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Missing")):
            pass
    assert websocket.closed is True


@pytest.mark.asyncio
async def test_qwen_provider_wraps_connect_failure_in_provider_error():
    async def connect(url, additional_headers):
        raise OSError("dns failed")

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="OSError"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Cherry")):
            pass


@pytest.mark.asyncio
async def test_qwen_provider_rejects_invalid_audio_delta_and_closes_websocket():
    websocket = FakeWebSocket([{"type": "response.audio.delta", "delta": "not base64!"}])

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="invalid audio delta"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Cherry")):
            pass
    assert websocket.closed is True


@pytest.mark.asyncio
async def test_qwen_provider_rejects_missing_audio_delta_and_closes_websocket():
    websocket = FakeWebSocket([{"type": "response.audio.delta"}])

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="invalid audio delta"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Cherry")):
            pass
    assert websocket.closed is True


@pytest.mark.asyncio
async def test_qwen_provider_close_error_does_not_mask_provider_error():
    websocket = FakeWebSocket([{"type": "error", "error": {"message": "bad voice"}}], close_error=RuntimeError("close failed"))

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="PROVIDER_ERROR"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Missing")):
            pass


def test_qwen_provider_build_url_preserves_query_and_urlencodes_model():
    provider = QwenTTSProvider(
        api_key="key",
        model="qwen 3/tts+flash",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime?workspace=abc",
    )

    assert provider._build_url() == "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime?workspace=abc&model=qwen+3%2Ftts%2Bflash"


class FakeWebSocket:
    def __init__(self, events, close_error=None):
        if not any(e.get('type') == 'session.created' for e in events) and type(self) is FakeWebSocket:
            events = [{'type': 'session.created'}, {'type': 'session.updated'}] + events
        self.events = [json.dumps(event) for event in events]
        self.sent_events = []
        self.closed = False
        self.close_error = close_error

    async def send(self, message):
        self.sent_events.append(json.loads(message))

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.events:
            raise StopAsyncIteration
        return self.events.pop(0)

    async def close(self):
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', ['session creation', 'session settings', 'audio'])
async def test_qwen_bounds_stalled_protocol_phases(phase):
    import asyncio
    class Stalled(FakeWebSocket):
        async def __anext__(self):
            if self.events:
                return await super().__anext__()
            await asyncio.Event().wait()
    events = [] if phase == 'session creation' else [{'type': 'session.created'}]
    if phase == 'audio':
        events.append({'type': 'session.updated'})
    ws = Stalled(events)
    async def connect(*args, **kwargs):
        return ws
    provider = QwenTTSProvider('key', 'model', 'wss://example.test', connect=connect,
                               setup_timeout=.02, audio_timeout=.02, segment_timeout=.2)
    with pytest.raises(ProviderError, match=phase):
        _ = [chunk async for chunk in provider.stream_speech('private text', TTSOptions(voice='Kai'))]
    assert ws.closed
    if phase != 'audio':
        assert not any(e['type'] == 'input_text_buffer.append' for e in ws.sent_events)


@pytest.mark.asyncio
async def test_qwen_waits_for_acknowledgements_and_retains_safe_diagnostics():
    class Ordered(FakeWebSocket):
        async def __anext__(self):
            e = await super().__anext__()
            kind = json.loads(e)['type']
            if kind == 'session.created':
                assert self.sent_events == []
            if kind == 'session.updated':
                assert [x['type'] for x in self.sent_events] == ['session.update']
            return e
    ws = Ordered([
        {'type': 'session.created', 'session': {'id': 'session-test'}},
        {'type': 'session.updated'},
        {'type': 'error', 'error': {'code': 'SERVER_ERROR', 'message': 'private text secret-key'}},
    ])
    async def connect(*args, **kwargs):
        return ws
    provider = QwenTTSProvider('secret-key', 'model', 'wss://example.test', connect=connect)
    with pytest.raises(ProviderError) as error:
        _ = [c async for c in provider.stream_speech('private text', TTSOptions(voice='Kai'))]
    assert 'SERVER_ERROR' in str(error.value) and 'session-test' in str(error.value)
    assert 'private text' not in str(error.value) and 'secret-key' not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('audio', [False, True])
async def test_qwen_non_audio_events_do_not_reset_deadline_and_total_is_bounded(audio):
    import asyncio
    class Endless(FakeWebSocket):
        async def __anext__(self):
            if self.events:
                return await super().__anext__()
            await asyncio.sleep(.002)
            return json.dumps({'type': 'response.audio.delta', 'delta': 'YQ=='} if audio else {'type': 'response.created'})
    ws = Endless([{'type': 'session.created'}, {'type': 'session.updated'}])
    async def connect(*args, **kwargs):
        return ws
    p = QwenTTSProvider('key', 'model', 'wss://example.test', connect=connect,
                        audio_timeout=.02, segment_timeout=.06)
    with pytest.raises(ProviderError, match='timed out'):
        _ = [c async for c in p.stream_speech('hello', TTSOptions(voice='Kai'))]
    assert ws.closed


@pytest.mark.asyncio
async def test_qwen_close_timeout_keeps_successful_audio():
    import asyncio
    class SlowClose(FakeWebSocket):
        async def close(self):
            await asyncio.Event().wait()
    ws = SlowClose([{'type': 'session.created'}, {'type': 'session.updated'},
                    {'type': 'response.audio.delta', 'delta': 'YQ=='},
                    {'type': 'response.done', 'response': {'status': 'completed'}}])
    async def connect(*args, **kwargs):
        return ws
    p = QwenTTSProvider('key', 'model', 'wss://example.test', connect=connect, close_timeout=.02)
    async with asyncio.timeout(.3):
        assert [c.data async for c in p.stream_speech('hello', TTSOptions(voice='Kai'))] == [b'a']


@pytest.mark.asyncio
@pytest.mark.parametrize('echo', ['private customer account', 'private\\ncustomer', 'private   customer'])
async def test_qwen_diagnostics_exclude_partial_and_escaped_input(echo, caplog):
    ws = FakeWebSocket([{'type': 'error', 'error': {'code': 'SERVER_ERROR', 'message': echo}}])
    async def connect(*args, **kwargs):
        return ws
    provider = QwenTTSProvider('secret-key', 'model', 'wss://example.test', connect=connect)
    with pytest.raises(ProviderError) as error:
        _ = [c async for c in provider.stream_speech('private customer account 12345. Additional content.', TTSOptions(voice='Kai'))]
    assert 'SERVER_ERROR' in str(error.value)
    assert 'private' not in str(error.value) + caplog.text


@pytest.mark.asyncio
async def test_qwen_transport_error_does_not_echo_request(caplog):
    async def connect(*args, **kwargs):
        raise OSError('Authorization: Bearer secret-key; private customer')
    provider = QwenTTSProvider('secret-key', 'model', 'wss://example.test', connect=connect)
    with pytest.raises(ProviderError) as error:
        _ = [c async for c in provider.stream_speech('private customer account', TTSOptions(voice='Kai'))]
    assert 'OSError' in str(error.value)
    assert 'private' not in str(error.value) + caplog.text
    assert 'secret-key' not in str(error.value) + caplog.text

import asyncio
from pathlib import Path

import pytest

from tts_app.events import EventBroker
from tts_app.generation import GenerationService
from tts_app.providers.base import AudioChunk, ProviderError
from tts_app.storage import Storage


class RecoveringProvider:
    name = 'fake'
    def __init__(self):
        self.calls = []
        self.fail = True
    async def stream_speech(self, text, options):
        self.calls.append((text, options))
        if text == 'Second.' and self.fail:
            raise ProviderError('temporary outage')
        yield AudioChunk(text.encode(), 'audio/mpeg', 'mp3')


def make_service(settings, provider):
    storage = Storage(settings.db_path)
    storage.init_schema()
    return GenerationService(storage, provider, EventBroker(), settings.audio_dir, 20)


@pytest.mark.asyncio
async def test_resume_skips_completed_audio_and_keeps_snapshot(test_settings):
    from tts_app.generation_jobs import GenerationJobs
    provider = RecoveringProvider()
    service = make_service(test_settings, provider)
    jobs = GenerationJobs(service)
    snapshot = dict(model='saved-model', voice='Original', language='en', speed=1.25, instructions='Calm')
    gid = await service.create_from_text('First.\n\nSecond.\n\nThird.', 'test', settings=snapshot)
    await jobs.start(gid, inline=True)
    before = service.storage.get_generation(gid)
    audio = before['audio_segments'][0]
    first = test_settings.data_dir / audio['file_path']
    original = first.read_bytes(), first.stat().st_mtime_ns
    assert before['generation']['status'] == 'failed'
    service.storage.update_generation_progress(gid, 0)
    provider.fail = False
    await jobs.start(gid, resume=True, inline=True)
    after = service.storage.get_generation(gid)
    assert after['generation']['status'] == 'completed'
    assert after['audio_segments'][0] == audio
    assert (first.read_bytes(), first.stat().st_mtime_ns) == original
    assert [text for text, _ in provider.calls] == ['First.', 'Second.', 'Second.', 'Third.']
    assert all(o.voice == 'Original' and o.model == 'saved-model' and o.speed == 1.25 and o.instructions == 'Calm' for _, o in provider.calls)
    assert (test_settings.audio_dir / str(gid) / 'full.mp3').read_bytes() == b'First.Second.Third.'


@pytest.mark.asyncio
async def test_owned_job_survives_submitter_cancellation_and_rejects_duplicates(test_settings):
    from tts_app.generation_jobs import GenerationJobs, GenerationConflict
    gate, entered = asyncio.Event(), asyncio.Event()
    class Slow(RecoveringProvider):
        async def stream_speech(self, text, options):
            entered.set()
            await gate.wait()
            yield AudioChunk(b'audio', 'audio/mpeg', 'mp3')
    service = make_service(test_settings, Slow())
    jobs = GenerationJobs(service)
    gid = await service.create_from_text('First.', 'test')
    submitter = asyncio.create_task(jobs.start(gid, inline=True))
    await entered.wait()
    submitter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await submitter
    assert service.storage.get_generation(gid)['generation']['status'] == 'running'
    with pytest.raises(GenerationConflict):
        await jobs.start(gid)
    gate.set()
    await jobs.wait(gid)
    assert service.storage.get_generation(gid)['generation']['status'] == 'completed'


@pytest.mark.asyncio
async def test_shutdown_and_restart_make_jobs_resumable(test_settings):
    from tts_app.generation_jobs import GenerationJobs
    entered = asyncio.Event()
    class Slow(RecoveringProvider):
        async def stream_speech(self, text, options):
            entered.set()
            await asyncio.Event().wait()
            yield
    service = make_service(test_settings, Slow())
    jobs = GenerationJobs(service)
    gid = await service.create_from_text('First.', 'test')
    await jobs.start(gid)
    await entered.wait()
    await jobs.shutdown()
    detail = service.storage.get_generation(gid)
    assert detail['generation']['status'] == 'failed'
    assert 'interrupted' in detail['generation']['error'].lower()
    assert detail['text_segments'][0]['status'] == 'failed'
    other = await service.create_from_text('Queued.', 'queued')
    service.storage.interrupt_generations()
    assert service.storage.get_generation(other)['generation']['status'] == 'failed'


@pytest.mark.asyncio
async def test_resume_refuses_missing_completed_file(test_settings):
    from tts_app.generation_jobs import GenerationJobs
    provider = RecoveringProvider()
    service = make_service(test_settings, provider)
    jobs = GenerationJobs(service)
    gid = await service.create_from_text('First.\n\nSecond.', 'test', settings=dict(model='model', voice='Kai', language='en', speed=1))
    await jobs.start(gid, inline=True)
    first = service.storage.get_generation(gid)['audio_segments'][0]
    (test_settings.data_dir / first['file_path']).unlink()
    with pytest.raises(ValueError, match='completed audio'):
        await jobs.start(gid, resume=True)
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_http_disconnect_restart_and_resume_use_saved_text(test_settings, monkeypatch):
    import httpx
    from tts_app import api
    from tts_app.providers.fake import FakeTTSProvider
    entered, release = asyncio.Event(), asyncio.Event()
    class Slow(FakeTTSProvider):
        async def stream_speech(self, text, options):
            entered.set()
            await release.wait()
            yield AudioChunk(b'checkpoint', 'audio/mpeg', 'mp3')
    monkeypatch.setattr(api, 'get_provider', lambda _: Slow())
    app = api.create_app(test_settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://test') as browser:
            response = await browser.post('/api/generations/text', json={'text':'Original text.'})
            gid = response.json()['generation_id']
        # The browser client has closed; work still belongs to the server.
        await asyncio.wait_for(entered.wait(), 1)
        assert app.state.storage.get_generation(gid)['generation']['status'] == 'running'
        release.set()
        await app.state.jobs.wait(gid)
        assert app.state.storage.get_generation(gid)['generation']['status'] == 'completed'
    # Emulate an unclean process exit after a durable claim.
    orphan = app.state.storage.create_generation(source_type='url',title='interrupted',url='https://example.test',
        full_text='Saved text.',provider='fake',voice='Kai',settings=dict(model='original-model',voice='Kai',language='en',speed=1))
    app.state.storage.create_text_segments(orphan, ['Saved text.'])
    app.state.storage.claim_generation(orphan)
    restarted = api.create_app(test_settings, run_background_inline=True)
    async with restarted.router.lifespan_context(restarted):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url='http://test') as browser:
            detail = (await browser.get(f'/api/generations/{orphan}')).json()
            assert detail['generation']['can_resume']
            assert 'interrupted' in detail['generation']['error'].lower()
            assert (await browser.post(f'/api/generations/{orphan}/resume')).status_code == 200
            assert (await browser.post(f'/api/generations/{orphan}/resume')).status_code == 409
            assert (await browser.post('/api/generations/99999/resume')).status_code == 404


@pytest.mark.asyncio
async def test_delete_cancels_job_before_removing_storage(test_settings, monkeypatch):
    import httpx
    from tts_app import api
    from tts_app.providers.fake import FakeTTSProvider
    entered, cancelled = asyncio.Event(), asyncio.Event()
    class Slow(FakeTTSProvider):
        async def stream_speech(self, text, options):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
            yield
    monkeypatch.setattr(api, 'get_provider', lambda _: Slow())
    app = api.create_app(test_settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as browser:
            gid = (await browser.post('/api/generations/text', json={'text':'Hello'})).json()['generation_id']
            await entered.wait()
            assert (await browser.delete(f'/api/generations/{gid}')).status_code == 204
            assert cancelled.is_set()
            assert (await browser.get(f'/api/generations/{gid}')).status_code == 404
            assert not (test_settings.audio_dir / str(gid)).exists()
            assert not app.state.jobs.tasks


@pytest.mark.asyncio
async def test_legacy_snapshot_cannot_resume_with_guessed_model(test_settings):
    from tts_app.generation_jobs import GenerationJobs
    service = make_service(test_settings, RecoveringProvider())
    gid = await service.create_from_text('First.', 'legacy')
    service.storage.update_generation_status(gid, 'failed', 'old failure')
    with pytest.raises(ValueError, match='not fully recorded'):
        await GenerationJobs(service).start(gid, resume=True)
    assert not service.provider.calls


def test_atomic_checkpoint_rolls_back_audio_if_text_status_update_fails(test_settings):
    import sqlite3
    service = make_service(test_settings, RecoveringProvider())
    storage = service.storage
    gid = storage.create_generation(source_type='text', title='test', url=None, full_text='Text', provider='fake', voice='Kai', settings={})
    sid = storage.create_text_segments(gid, ['Text'])[0]
    with storage.connection() as conn:
        conn.execute("CREATE TRIGGER fail_checkpoint BEFORE UPDATE ON text_segments BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='disk failure'):
        storage.complete_audio_segment(generation_id=gid,text_segment_id=sid,segment_index=0,file_path='audio/test.mp3',mime_type='audio/mpeg',duration_ms=None,byte_size=5)
    detail = storage.get_generation(gid)
    assert detail['text_segments'][0]['status'] == 'queued'
    assert detail['audio_segments'] == []


@pytest.mark.asyncio
async def test_resume_recovers_after_audio_file_written_but_metadata_failed(test_settings, monkeypatch):
    from tts_app.generation_jobs import GenerationJobs
    service = make_service(test_settings, RecoveringProvider())
    jobs = GenerationJobs(service)
    gid = await service.create_from_text('First.', 'test', settings=dict(model='model',voice='Kai',speed=1,language='en'))
    complete = service.storage.complete_audio_segment
    def fail(**kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(service.storage, 'complete_audio_segment', fail)
    await jobs.start(gid, inline=True)
    detail = service.storage.get_generation(gid)
    assert detail['generation']['status'] == 'failed' and detail['audio_segments'] == []
    monkeypatch.setattr(service.storage, 'complete_audio_segment', complete)
    await jobs.start(gid, resume=True, inline=True)
    assert len(service.storage.get_generation(gid)['audio_segments']) == 1
    assert (test_settings.audio_dir / str(gid) / 'full.mp3').read_bytes() == b'First.'


@pytest.mark.parametrize('field,value', [('speed',float('nan')),('speed',False),('speed',5),('language','xx'),('model',12),('voice','')])
def test_invalid_snapshot_not_offered_for_resume(field, value):
    from tts_app.generation_jobs import resume_unavailable_reason
    settings = dict(model='model', voice='Kai', speed=1, language='en')
    settings[field] = value
    assert resume_unavailable_reason(dict(status='failed',provider='fake',settings=settings),'fake')

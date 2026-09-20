"""Single-process ownership of generation tasks, independent of HTTP/browser lifetime."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import math

from tts_app.generation_storage import GenerationConflict

logger = logging.getLogger(__name__)


def resume_unavailable_reason(generation, provider_name):
    if generation['status'] != 'failed':
        return 'Only failed or interrupted generations can be resumed.'
    if generation['provider'] != provider_name:
        return 'The original speech provider is not configured.'
    settings = generation['settings']
    if not all(isinstance(settings.get(key), str) and settings[key].strip() for key in ('model', 'voice', 'language')) or 'speed' not in settings:
        return 'Original synthesis settings were not fully recorded. Create a new generation.'
    speed = settings['speed']
    if (isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed)
            or not .5 <= speed <= 2 or settings['language'] not in {'en', 'zh'}
            or not isinstance(settings.get('instructions', ''), str)):
        return 'Original synthesis settings are invalid. Create a new generation.'
    return None


class GenerationJobs:
    def __init__(self, service):
        self.service = service
        self.tasks = {}
        self.deleting_ids = set()
        self.closing = False

    async def start(self, generation_id, *, resume=False, inline=False, voice='Test', speed=1.0, language='Auto'):
        if self.closing or generation_id in self.tasks or generation_id in self.deleting_ids:
            raise GenerationConflict('Generation is already active or is being stopped.')
        detail = self.service.storage.get_generation(generation_id)
        if resume:
            if detail['generation']['status'] != 'failed':
                raise GenerationConflict('Only failed or interrupted generations can be resumed.')
            reason = resume_unavailable_reason(detail['generation'], self.service.provider.name)
            if reason:
                raise ValueError(reason)
            self.service.validate_completed_audio(detail)
        self.service.storage.claim_generation(generation_id, resume=resume)
        # No await between the durable claim and task registration.
        self.service.broker.clear_history(generation_id)
        task = asyncio.create_task(self._run(generation_id, voice, speed, language), name=f'generation-{generation_id}')
        self.tasks[generation_id] = task
        if inline:
            await asyncio.shield(task)

    async def _run(self, generation_id, voice, speed, language):
        try:
            await self.service.run_generation(generation_id, voice, speed, language)
        except asyncio.CancelledError:
            self.service.storage.interrupt_generations(generation_id)
            raise
        except Exception:
            logger.exception('generation_job_failed generation_id=%s', generation_id)
            self.service.storage.update_generation_status(generation_id, 'failed', 'Generation stopped unexpectedly. Resume to continue.')
            await self.service.broker.publish(generation_id, {'type': 'generation_failed', 'generation_id': generation_id, 'error': 'Generation stopped unexpectedly. Resume to continue.'})
        finally:
            self.tasks.pop(generation_id, None)

    async def wait(self, generation_id):
        task = self.tasks.get(generation_id)
        if task:
            await asyncio.shield(task)

    async def cancel(self, generation_id):
        task = self.tasks.get(generation_id)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            # A task cancelled before its first instruction never enters _run.
            self.tasks.pop(generation_id, None)
            self.service.storage.interrupt_generations(generation_id)

    @asynccontextmanager
    async def deleting(self, generation_id):
        if generation_id in self.deleting_ids:
            raise GenerationConflict('Generation is already being deleted.')
        self.deleting_ids.add(generation_id)
        try:
            await self.cancel(generation_id)
            yield
        finally:
            self.deleting_ids.discard(generation_id)

    async def shutdown(self):
        self.closing = True
        await asyncio.gather(*(self.cancel(gid) for gid in list(self.tasks)))

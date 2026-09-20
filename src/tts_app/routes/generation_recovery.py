"""Resume existing generations without re-extraction or mutable profile lookup."""
from fastapi import APIRouter, HTTPException
from tts_app.generation_storage import GenerationConflict


def create_generation_recovery_router(jobs, *, run_background_inline=False):
    router = APIRouter()

    @router.post('/api/generations/{generation_id}/resume')
    async def resume_generation(generation_id: int):
        try:
            await jobs.start(generation_id, resume=True, inline=run_background_inline)
        except KeyError as exc:
            raise HTTPException(404, 'generation not found') from exc
        except GenerationConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {'generation_id': generation_id}

    return router


def add_recovery_status(generation, provider_name):
    from tts_app.generation_jobs import resume_unavailable_reason
    reason = resume_unavailable_reason(generation, provider_name)
    return {**generation, 'can_resume': reason is None,
            'resume_unavailable_reason': reason if generation['status'] == 'failed' else None}

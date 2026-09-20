from __future__ import annotations

from fastapi import BackgroundTasks

from tts_app.generation import GenerationService


async def schedule_generation(
    service: GenerationService,
    generation_id: int,
    voice: str,
    speed: float,
    language: str,
    background_tasks: BackgroundTasks,
    run_background_inline: bool,
) -> None:
    if run_background_inline:
        await service.jobs.start(generation_id, voice=voice, speed=speed, language=language, inline=True)
        return
    await service.jobs.start(generation_id, voice=voice, speed=speed, language=language)
